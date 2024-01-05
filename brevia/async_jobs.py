"""Async Jobs table & utilities"""
import importlib
import logging
import time
from datetime import datetime
import sqlalchemy
from sqlalchemy.dialects.postgresql import JSON, TIMESTAMP, SMALLINT
from sqlalchemy.orm import Session
from langchain_community.vectorstores.pgembedding import BaseModel
from brevia.connection import db_connection
from brevia.services import BaseService

MAX_DURATION = 120  # default max duration is 120 min / 2hr
MAX_ATTEMPTS = 1  # default max number of attempts


class AsyncJobsStore(BaseModel):
    # pylint: disable=too-few-public-methods,not-callable
    """ Async Jobs table """
    __tablename__ = "async_jobs"

    service = sqlalchemy.Column(sqlalchemy.String(), nullable=False)
    payload = sqlalchemy.Column(JSON())
    expires = sqlalchemy.Column(TIMESTAMP(timezone=False))
    created = sqlalchemy.Column(
        TIMESTAMP(timezone=False),
        nullable=False,
        server_default=sqlalchemy.func.current_timestamp(),
    )
    completed = sqlalchemy.Column(TIMESTAMP(timezone=False))
    locked_until = sqlalchemy.Column(TIMESTAMP(timezone=False))
    max_attempts = sqlalchemy.Column(
        SMALLINT(),
        nullable=False,
        server_default='1',
    )
    result = sqlalchemy.Column(JSON(), nullable=True)


def single_job(uuid: str) -> (AsyncJobsStore | None):
    """ Get single job by UUID """
    with Session(db_connection()) as session:
        return session.get(AsyncJobsStore, uuid)


def create_job(
    service: str,
    payload: dict,
) -> AsyncJobsStore:
    """ Create async job """
    max_duration = payload.get('max_duration', MAX_DURATION)  # max duration in minutes
    max_attempts = payload.get('max_attempts', MAX_ATTEMPTS)
    tstamp = int(time.time()) + (max_duration * max_attempts * 2 * 60)
    expires = datetime.fromtimestamp(tstamp)

    with Session(db_connection()) as session:
        job_store = AsyncJobsStore(
            service=service,
            payload=payload,
            expires=expires,
            max_attempts=max_attempts,
        )
        session.expire_on_commit = False
        session.add(job_store)
        session.commit()

        return job_store


def complete_job(
    uuid: str,
    result: dict,
) -> None:
    """ Complete async job with result """
    # pylint: disable=broad-exception-caught
    log = logging.getLogger(__name__)
    job_store = single_job(uuid)
    if not job_store:
        log.error("Job %s not found", uuid)
        return
    now = datetime.now()
    if job_store.expires and job_store.expires < now:
        log.warning("Job %s is expired at %s", uuid, job_store.expires)
        return

    try:
        save_job_result(job_store=job_store, result=result)
    except Exception as exc:
        msg = exc.args[0]
        log.error("Error completing job - %s", msg)
        result = {'error': msg}
        try:
            save_job_result(job_store=job_store, result=result, error=True)
        except Exception as ex2:
            log.error("Error saving job error - %s", ex2.args[0])


def save_job_result(job_store: AsyncJobsStore, result: dict, error: bool = False):
    """Save Job result"""
    with Session(db_connection()) as session:
        job_store.completed = datetime.now()
        job_store.result = result
        if error:
            job_store.max_attempts = max(job_store.max_attempts - 1, 0)
        session.add(job_store)
        session.expire_on_commit = False
        session.commit()


def create_service(service: str) -> BaseService:
    """ Create job service from string """
    module_name, class_name = service.rsplit('.', 1)
    module = importlib.import_module(module_name)
    if not hasattr(module, class_name):
        raise ValueError(f'Class "{class_name}" not found in "{module}"')
    service_class = getattr(module, class_name)
    if not issubclass(service_class, BaseService):
        raise ValueError(f'Class "{class_name}" must extend "BaseService"')

    return service_class()


def run_job_service(
    uuid: str,
) -> None:
    """ Create run job service """
    log = logging.getLogger(__name__)
    job_store = single_job(uuid)
    if not job_store:
        log.error("Job %s not found", uuid)
        return
    result = {}

    try:
        lock_job_service(job_store)
        service = create_service(job_store.service)
        result = service.run(job_store.payload)

    except Exception as exc:  # pylint: disable=broad-exception-caught
        msg = f'{type(exc).__name__}: {exc}'
        log.error('Error in job service %s: %s', job_store.service, msg)
        result = {'error': msg}

    finally:
        complete_job(uuid=uuid, result=result)


def lock_job_service(
    job_store: AsyncJobsStore
) -> None:
    """Lock job service"""
    if not is_job_available(job_store):
        raise RuntimeError(f'Job {job_store.uuid} is not available')
    payload = job_store.payload if job_store.payload else {}
    tstamp = int(time.time()) + (int(payload.get('max_duration', MAX_DURATION)) * 60)
    locked_until = datetime.fromtimestamp(tstamp)

    with Session(db_connection()) as session:
        job_store.locked_until = locked_until
        session.add(job_store)
        session.expire_on_commit = False
        session.commit()


def is_job_available(
    job_store: AsyncJobsStore
) -> bool:
    """Check if job is available"""
    now = datetime.now()
    if job_store.completed or (job_store.expires and job_store.expires < now):
        return False
    if job_store.locked_until and (job_store.locked_until > now):
        return False
    if job_store.max_attempts <= 0:
        return False

    return True
