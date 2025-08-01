"""async_jobs module tests"""
from datetime import datetime, timedelta
import time
import pytest
from unittest.mock import patch
from sqlalchemy.orm import Session
from brevia.connection import db_connection
from brevia.async_jobs import (
    single_job, create_job, complete_job,
    save_job_result, create_service, lock_job_service,
    is_job_available, run_job_service, get_jobs, JobsFilter,
    cleanup_async_jobs, AsyncJobsStore,
)
from brevia.services import BaseService


def test_create_and_get_job():
    """ Test create_job and single_job functions """
    service = 'test_service'
    payload = {'max_duration': 10, 'max_attempts': 3}
    job = create_job(service, payload)
    assert job is not None
    assert isinstance(job.expires, datetime)

    # Retrieve the job by UUID and check if it matches
    retrieved_job = single_job(job.uuid)
    assert retrieved_job is not None
    assert retrieved_job.uuid == job.uuid
    assert retrieved_job.service == service


def test_complete_job():
    """ Test complete_job function """
    service = 'test_service'
    payload = {'max_duration': 10, 'max_attempts': 3}
    job = create_job(service, payload)
    assert job is not None

    # Attempt to complete the job with a result
    result = {'key': 'value'}
    complete_job(job.uuid, result)

    # Retrieve the completed job and check if it was updated correctly
    retrieved_job = single_job(job.uuid)
    assert retrieved_job is not None
    assert 'key' in retrieved_job.result
    assert retrieved_job.result['key'] == 'value'

    # Test for expired job
    with Session(db_connection()) as session:
        retrieved_job.expires = datetime.now() - timedelta(days=1)
        retrieved_job.result = {}
        session.add(retrieved_job)
        session.commit()

    complete_job(job.uuid, result)

    # Verify that the job was not updated if it's expired
    retrieved_job = single_job(job.uuid)
    assert retrieved_job is not None
    assert 'key' not in retrieved_job.result


def test_save_job_result():
    """ Create a job and set the result """
    service = 'test_service'
    payload = {'max_duration': 10, 'max_attempts': 3}
    job = create_job(service, payload)
    assert job is not None

    # Save a result for the job
    result = {"key": "value"}
    save_job_result(job, result)

    # Verify that the job's result was updated
    retrieved_job = single_job(job.uuid)
    assert retrieved_job is not None
    assert retrieved_job.result == result


def test_create_service():
    """ Test create_service function """
    service_name = 'brevia.services.FakeService'
    service = create_service(service_name)
    assert isinstance(service, BaseService)


def test_lock_and_is_job_available():
    """ Create a job and lock it """
    service = 'brevia.services.FakeService'
    payload = {'max_duration': 10, 'max_attempts': 3}
    job = create_job(service, payload)
    assert job is not None

    lock_job_service(job)

    # Verify that the job is locked
    assert is_job_available(job) is False

    # Attempt to lock an already locked job
    with pytest.raises(RuntimeError) as exc:
        lock_job_service(job)
    assert str(exc.value) == f'Job {job.uuid} is not available'


def test_run_job_service():
    """ Create a job, run the job service, and complete it """
    service = 'brevia.services.FakeService'
    payload = {'max_duration': 10, 'max_attempts': 3}
    job = create_job(service, payload)
    assert job is not None
    run_job_service(job.uuid)

    # Verify that the job is completed
    retrieved_job = single_job(job.uuid)
    assert retrieved_job is not None
    assert retrieved_job.completed is not None
    assert retrieved_job.result == {'output': 'ok'}


def test_run_job_failure():
    """ Test run job service failure """
    service = 'brevia.services.NotExistingService'
    job = create_job(service, {})
    assert job is not None
    run_job_service(job.uuid)

    # Verify that the job is completed
    retrieved_job = single_job(job.uuid)
    assert retrieved_job is not None
    assert retrieved_job.completed is not None
    exp = 'ValueError: Class "NotExistingService" not found'
    assert 'error' in retrieved_job.result
    assert retrieved_job.result['error'].startswith(exp)


def test_get_jobs_no_filters():
    """Test get_jobs function without filters"""
    # Create some test jobs
    job1 = create_job('TestService1', {'test': 'data1'})
    job2 = create_job('TestService2', {'test': 'data2'})

    # Get jobs without filters
    filter_obj = JobsFilter()
    result = get_jobs(filter_obj)

    # Verify response structure
    assert isinstance(result, dict)
    assert 'data' in result
    assert 'meta' in result
    assert 'pagination' in result['meta']

    # Verify pagination structure
    pagination = result['meta']['pagination']
    assert 'page' in pagination
    assert 'count' in pagination
    assert 'page_count' in pagination

    # Verify we have at least our test jobs
    assert len(result['data']) >= 2

    # Verify job data structure
    job_uuids = [str(job1.uuid), str(job2.uuid)]
    found_jobs = [job for job in result['data'] if str(job['uuid']) in job_uuids]
    assert len(found_jobs) >= 2


def test_get_jobs_with_service_filter():
    """Test get_jobs function with service filter"""
    # Create jobs with different services
    service_name = f'FilterTestService_{int(time.time())}'
    job1 = create_job(service_name, {'test': 'data1'})
    job2 = create_job('DifferentService', {'test': 'data2'})

    # Filter by specific service
    filter_obj = JobsFilter(service=service_name)
    result = get_jobs(filter_obj)

    assert 'data' in result
    assert len(result['data']) >= 1

    # All returned jobs should have the specified service
    for job in result['data']:
        if str(job['uuid']) == str(job1.uuid):
            assert job['service'] == service_name

    # Verify the other job is not included when filtering
    other_job_found = any(str(job['uuid']) == str(job2.uuid) for job in result['data'])
    if other_job_found:
        # If found, it should also have the same service (which shouldn't happen)
        other_job_service = next(
            job['service'] for job in result['data']
            if str(job['uuid']) == str(job2.uuid)
        )
        assert other_job_service == service_name
    else:
        # This is the expected case - other job should not be found
        assert not other_job_found


def test_get_jobs_with_completed_filter():
    """Test get_jobs function with completed filter"""
    # Create jobs and complete one of them
    job1 = create_job('CompletedTestService', {'test': 'completed'})
    job2 = create_job('IncompleteTestService', {'test': 'incomplete'})

    # Complete the first job
    complete_job(str(job1.uuid), {'result': 'success'})

    # Filter for completed jobs
    filter_obj = JobsFilter(completed=True)
    result = get_jobs(filter_obj)

    assert 'data' in result

    # Find our completed job in the results
    completed_job_found = None
    for job in result['data']:
        if str(job['uuid']) == str(job1.uuid):
            completed_job_found = job
            break

    assert completed_job_found is not None
    assert completed_job_found['completed'] is not None

    # Filter for incomplete jobs
    filter_obj = JobsFilter(completed=False)
    result = get_jobs(filter_obj)

    assert 'data' in result

    # Find our incomplete job in the results
    incomplete_job_found = None
    for job in result['data']:
        if str(job['uuid']) == str(job2.uuid):
            incomplete_job_found = job
            break

    assert incomplete_job_found is not None
    assert incomplete_job_found['completed'] is None


def test_get_jobs_with_date_filters():
    """Test get_jobs function with date filters"""
    # Create a job
    job = create_job('DateTestService', {'test': 'date_filter'})

    # Get current date for filtering
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')

    # Test with min_date filter
    filter_obj = JobsFilter(min_date=yesterday)
    result = get_jobs(filter_obj)

    assert 'data' in result
    # Our job should be included since it was created today (after yesterday)
    job_found = any(
        str(job_data['uuid']) == str(job.uuid) for job_data in result['data']
    )
    assert job_found

    # Test with max_date filter
    filter_obj = JobsFilter(max_date=tomorrow)
    result = get_jobs(filter_obj)

    assert 'data' in result
    # Our job should be included since it was created today (before tomorrow)
    job_found = any(
        str(job_data['uuid']) == str(job.uuid) for job_data in result['data']
    )
    assert job_found

    # Test with both min_date and max_date
    filter_obj = JobsFilter(min_date=yesterday, max_date=tomorrow)
    result = get_jobs(filter_obj)

    assert 'data' in result
    job_found = any(
        str(job_data['uuid']) == str(job.uuid) for job_data in result['data']
    )
    assert job_found

    # Test with restrictive date range (future dates)
    future_date = (datetime.now() + timedelta(days=2)).strftime('%Y-%m-%d')
    filter_obj = JobsFilter(min_date=future_date)
    result = get_jobs(filter_obj)

    # Our job should not be included since it was created before the future date
    job_found = any(
        str(job_data['uuid']) == str(job.uuid) for job_data in result['data']
    )
    assert not job_found


def test_get_jobs_with_pagination():
    """Test get_jobs function with pagination"""
    # Create multiple jobs for pagination testing
    jobs = []
    for i in range(5):
        job = create_job(f'PaginationTestService_{i}', {'test': f'pagination_{i}'})
        jobs.append(job)

    # Test with custom page size
    filter_obj = JobsFilter(page=1, page_size=3)
    result = get_jobs(filter_obj)

    assert 'data' in result
    assert 'meta' in result
    assert 'pagination' in result['meta']

    pagination = result['meta']['pagination']
    assert pagination['page'] == 1
    assert len(result['data']) <= 3

    # Test second page
    filter_obj = JobsFilter(page=2, page_size=3)
    result = get_jobs(filter_obj)

    pagination = result['meta']['pagination']
    assert pagination['page'] == 2


def test_get_jobs_with_multiple_filters():
    """Test get_jobs function with multiple filters combined"""
    # Create a specific job for this test
    service_name = f'MultiFilterTest_{int(time.time())}'
    job = create_job(service_name, {'test': 'multi_filter'})

    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')

    # Test combining service, completed, and date filters
    filter_obj = JobsFilter(
        service=service_name,
        completed=False,
        min_date=yesterday,
        max_date=tomorrow,
        page_size=10
    )
    result = get_jobs(filter_obj)

    assert 'data' in result
    assert 'meta' in result
    assert 'pagination' in result['meta']

    # Find our specific job in the results
    target_job = None
    for job_data in result['data']:
        if str(job_data['uuid']) == str(job.uuid):
            target_job = job_data
            break

    assert target_job is not None
    assert target_job['service'] == service_name
    assert target_job['completed'] is None  # Should be incomplete


def test_get_jobs_empty_results():
    """Test get_jobs function with filters that return no results"""
    # Use a service name that doesn't exist
    non_existent_service = f'NonExistentService_{int(time.time())}'

    filter_obj = JobsFilter(service=non_existent_service)
    result = get_jobs(filter_obj)

    assert 'data' in result
    assert 'meta' in result
    assert 'pagination' in result['meta']
    assert len(result['data']) == 0

    pagination = result['meta']['pagination']
    assert pagination['count'] == 0


def test_cleanup_async_jobs_no_jobs():
    """Test cleanup_async_jobs when no jobs exist to delete"""
    # Use a future date to ensure no jobs are found
    future_date = datetime.now() + timedelta(days=1)

    # Test dry run with no jobs
    result = cleanup_async_jobs(before_date=future_date, dry_run=True)
    assert result == 0

    # Test actual cleanup with no jobs
    result = cleanup_async_jobs(before_date=future_date, dry_run=False)
    assert result == 0


def test_cleanup_async_jobs_dry_run():
    """Test cleanup_async_jobs dry run functionality"""
    # Create some test jobs
    service = 'test_cleanup_service'
    payload = {'max_duration': 10, 'max_attempts': 1}

    job1 = create_job(service, payload)
    job2 = create_job(service, payload)

    # Set created dates to the past for testing
    past_date = datetime.now() - timedelta(days=2)
    cutoff_date = datetime.now() - timedelta(days=1)

    with Session(db_connection()) as session:
        # Update job1 to have an old created date
        job1_store = session.get(AsyncJobsStore, job1.uuid)
        job1_store.created = past_date
        session.add(job1_store)
        session.commit()

    # Dry run should return count without deleting
    result = cleanup_async_jobs(before_date=cutoff_date, dry_run=True)
    assert result == 1

    # Verify job1 still exists
    retrieved_job = single_job(job1.uuid)
    assert retrieved_job is not None

    # Verify job2 still exists (should not be affected)
    retrieved_job2 = single_job(job2.uuid)
    assert retrieved_job2 is not None


def test_cleanup_async_jobs_actual_deletion():
    """Test cleanup_async_jobs actual deletion functionality"""
    # Create some test jobs
    service = 'test_cleanup_service_delete'
    payload = {'max_duration': 10, 'max_attempts': 1}

    job1 = create_job(service, payload)
    job2 = create_job(service, payload)
    job3 = create_job(service, payload)

    # Set different created dates
    old_date = datetime.now() - timedelta(days=3)
    cutoff_date = datetime.now() - timedelta(days=1)

    with Session(db_connection()) as session:
        # Update job1 and job2 to have old created dates
        job1_store = session.get(AsyncJobsStore, job1.uuid)
        job1_store.created = old_date
        session.add(job1_store)

        job2_store = session.get(AsyncJobsStore, job2.uuid)
        job2_store.created = old_date
        session.add(job2_store)

        session.commit()

    # Perform actual cleanup
    result = cleanup_async_jobs(before_date=cutoff_date, dry_run=False)
    assert result == 2

    # Verify job1 and job2 are deleted
    retrieved_job1 = single_job(job1.uuid)
    assert retrieved_job1 is None

    retrieved_job2 = single_job(job2.uuid)
    assert retrieved_job2 is None

    # Verify job3 still exists (created recently, not affected)
    retrieved_job3 = single_job(job3.uuid)
    assert retrieved_job3 is not None


def test_cleanup_async_jobs_with_timezone():
    """Test cleanup_async_jobs with timezone-aware datetime"""
    from datetime import timezone

    # Create a test job
    service = 'test_cleanup_timezone'
    payload = {'max_duration': 10, 'max_attempts': 1}

    job = create_job(service, payload)

    # Set created date to the past with timezone
    past_date = datetime.now(tz=timezone.utc) - timedelta(days=2)
    cutoff_date = datetime.now(tz=timezone.utc) - timedelta(days=1)

    with Session(db_connection()) as session:
        job_store = session.get(AsyncJobsStore, job.uuid)
        job_store.created = past_date
        session.add(job_store)
        session.commit()

    # Test with timezone-aware datetime
    result = cleanup_async_jobs(before_date=cutoff_date, dry_run=False)
    assert result == 1

    # Verify job is deleted
    retrieved_job = single_job(job.uuid)
    assert retrieved_job is None


@patch('brevia.async_jobs.LinkedFileOutput')
def test_cleanup_async_jobs_with_file_cleanup(mock_linked_file_output):
    """Test cleanup_async_jobs calls file cleanup for each deleted job"""
    from datetime import timezone

    # Create test jobs
    service = 'test_cleanup_with_files'
    payload = {'max_duration': 10, 'max_attempts': 1}

    job1 = create_job(service, payload)
    job2 = create_job(service, payload)

    # Set created dates to the past
    past_date = datetime.now(tz=timezone.utc) - timedelta(days=2)
    cutoff_date = datetime.now(tz=timezone.utc) - timedelta(days=1)

    with Session(db_connection()) as session:
        # Update both jobs to have old created dates
        job1_store = session.get(AsyncJobsStore, job1.uuid)
        job1_store.created = past_date
        session.add(job1_store)

        job2_store = session.get(AsyncJobsStore, job2.uuid)
        job2_store.created = past_date
        session.add(job2_store)

        session.commit()

    # Mock the LinkedFileOutput instance and cleanup method
    mock_instance = mock_linked_file_output.return_value
    mock_instance.cleanup_job_files.return_value = None

    # Perform actual cleanup
    result = cleanup_async_jobs(before_date=cutoff_date, dry_run=False)
    assert result == 2

    # Verify LinkedFileOutput was called for each job
    assert mock_linked_file_output.call_count == 2
    mock_linked_file_output.assert_any_call(job_id=str(job1.uuid))
    mock_linked_file_output.assert_any_call(job_id=str(job2.uuid))

    # Verify cleanup_job_files was called for each job
    assert mock_instance.cleanup_job_files.call_count == 2

    # Verify jobs are deleted from database
    assert single_job(job1.uuid) is None
    assert single_job(job2.uuid) is None


@patch('brevia.async_jobs.LinkedFileOutput')
def test_cleanup_async_jobs_file_cleanup_error(mock_linked_file_output):
    """Test cleanup_async_jobs handles file cleanup errors gracefully"""
    from datetime import timezone

    # Create a test job
    service = 'test_cleanup_error'
    payload = {'max_duration': 10, 'max_attempts': 1}
    job = create_job(service, payload)

    # Set created date to the past
    past_date = datetime.now(tz=timezone.utc) - timedelta(days=2)
    cutoff_date = datetime.now(tz=timezone.utc) - timedelta(days=1)

    with Session(db_connection()) as session:
        job_store = session.get(AsyncJobsStore, job.uuid)
        job_store.created = past_date
        session.add(job_store)
        session.commit()

    # Mock the LinkedFileOutput to raise an exception during cleanup
    mock_instance = mock_linked_file_output.return_value
    mock_instance.cleanup_job_files.side_effect = Exception("File cleanup failed")

    # Perform cleanup - should not fail despite file cleanup error
    result = cleanup_async_jobs(before_date=cutoff_date, dry_run=False)
    assert result == 1

    # Verify job is still deleted from database despite file cleanup error
    assert single_job(job.uuid) is None

    # Verify cleanup was attempted
    mock_linked_file_output.assert_called_once_with(job_id=str(job.uuid))
    mock_instance.cleanup_job_files.assert_called_once()


def test_cleanup_async_jobs_dry_run_no_file_cleanup():
    """Test cleanup_async_jobs dry run does not call file cleanup"""
    # Create a test job
    service = 'test_dry_run_no_cleanup'
    payload = {'max_duration': 10, 'max_attempts': 1}
    job = create_job(service, payload)

    # Set created date to the past
    past_date = datetime.now() - timedelta(days=2)
    cutoff_date = datetime.now() - timedelta(days=1)

    with Session(db_connection()) as session:
        job_store = session.get(AsyncJobsStore, job.uuid)
        job_store.created = past_date
        session.add(job_store)
        session.commit()

    with patch('brevia.async_jobs.LinkedFileOutput') as mock_linked_file_output:
        # Perform dry run
        result = cleanup_async_jobs(before_date=cutoff_date, dry_run=True)
        assert result == 1

        # Verify LinkedFileOutput was not called in dry run
        mock_linked_file_output.assert_not_called()

        # Verify job still exists after dry run
        assert single_job(job.uuid) is not None
