"""async_jobs module tests"""
from datetime import datetime, timedelta
import pytest
from sqlalchemy.orm import Session
from brevia.connection import db_connection
from brevia.async_jobs import (
    single_job, create_job, complete_job,
    save_job_result, create_service, lock_job_service,
    is_job_available, run_job_service,
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
