"""Jobs router tests"""
import uuid
import time
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from fastapi import FastAPI
from brevia.routers import jobs_router
from brevia.async_jobs import create_job, complete_job

app = FastAPI()
app.include_router(jobs_router.router)
client = TestClient(app)


def test_jobs_ok():
    """Test /jobs/{uuid} success"""
    job = create_job('TestService', {})
    response = client.get(f'/jobs/{job.uuid}', headers={})
    assert response.status_code == 200
    data = response.json()
    assert data is not None
    assert data['uuid'] == str(job.uuid)


def test_jobs_fail():
    """Test /jobs/{uuid} failure"""
    response = client.get(f'/jobs/{uuid.uuid4()}', headers={})
    assert response.status_code == 404


def test_jobs_list_no_filters():
    """Test /jobs endpoint without filters"""
    # Create some test jobs
    create_job('TestService1', {'test': 'data1'})
    create_job('TestService2', {'test': 'data2'})

    response = client.get('/jobs', headers={})
    assert response.status_code == 200
    data = response.json()

    assert 'data' in data
    assert 'meta' in data
    assert 'pagination' in data['meta']
    assert isinstance(data['data'], list)
    assert len(data['data']) >= 2  # At least our test jobs should be present

    # Check pagination structure
    pagination = data['meta']['pagination']
    assert 'page' in pagination
    assert 'page_count' in pagination
    assert 'count' in pagination


def test_jobs_list_with_service_filter():
    """Test /jobs endpoint with service filter"""
    # Create jobs with different services
    service_name = f'FilterTestService_{int(time.time())}'
    create_job(service_name, {'test': 'data1'})
    create_job('DifferentService', {'test': 'data2'})

    # Test filtering by service
    response = client.get(f'/jobs?service={service_name}', headers={})
    assert response.status_code == 200
    data = response.json()

    assert 'data' in data
    assert len(data['data']) == 1

    # All returned jobs should have the specified service
    for job in data['data']:
        assert job['service'] == service_name


def test_jobs_list_with_completed_filter():
    """Test /jobs endpoint with completed filter"""
    # Create a job and complete it
    job1 = create_job('CompletedTestService', {'test': 'completed'})
    complete_job(str(job1.uuid), {'result': 'success'})

    # Create an incomplete job
    job2 = create_job('IncompleteTestService', {'test': 'incomplete'})

    # Test filtering for completed jobs
    response = client.get('/jobs?completed=true', headers={})
    assert response.status_code == 200
    data = response.json()

    assert 'data' in data
    # All returned jobs should have completed timestamp
    for job in data['data']:
        if job['uuid'] == str(job1.uuid):
            assert job['completed'] is not None

    # Test filtering for incomplete jobs
    response = client.get('/jobs?completed=false', headers={})
    assert response.status_code == 200
    data = response.json()

    assert 'data' in data
    # All returned jobs should not have completed timestamp
    for job in data['data']:
        if job['uuid'] == str(job2.uuid):
            assert job['completed'] is None


def test_jobs_list_with_date_filters():
    """Test /jobs endpoint with date filters"""
    # Create a job
    create_job('DateTestService', {'test': 'date_filter'})

    # Get current date for filtering
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')

    # Test with min_date filter
    response = client.get(f'/jobs?min_date={yesterday}', headers={})
    assert response.status_code == 200
    data = response.json()
    assert 'data' in data

    # Test with max_date filter
    response = client.get(f'/jobs?max_date={tomorrow}', headers={})
    assert response.status_code == 200
    data = response.json()
    assert 'data' in data

    # Test with both min_date and max_date
    response = client.get(f'/jobs?min_date={yesterday}&max_date={tomorrow}', headers={})
    assert response.status_code == 200
    data = response.json()
    assert 'data' in data


def test_jobs_list_with_multiple_filters():
    """Test /jobs endpoint with multiple filters combined"""
    # Create a specific job for this test
    service_name = f'MultiFilterTest_{int(time.time())}'
    job = create_job(service_name, {'test': 'multi_filter'})

    today = datetime.now().strftime('%Y-%m-%d')
    tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')

    # Test combining service, completed, and date filters
    params = (
        f'service={service_name}&completed=false&'
        f'min_date={today}&max_date={tomorrow}&page_size=10'
    )
    response = client.get(
        f'/jobs?{params}',
        headers={}
    )
    assert response.status_code == 200
    data = response.json()

    assert 'data' in data
    assert 'meta' in data
    assert 'pagination' in data['meta']

    # Verify that the response structure is correct
    for job_data in data['data']:
        if job_data['uuid'] == str(job.uuid):
            assert job_data['service'] == service_name
            assert job_data['completed'] is None  # Should be incomplete
