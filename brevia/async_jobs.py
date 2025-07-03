"""Async Jobs table & utilities"""
import logging
import time
from datetime import datetime
from sqlalchemy import BinaryExpression, Column, desc, func, String, text
from pydantic import BaseModel as PydanticModel
from sqlalchemy.dialects.postgresql import JSON, TIMESTAMP, SMALLINT
from sqlalchemy.orm import Session, Query
from langchain_community.vectorstores.pgembedding import BaseModel
from brevia.connection import db_connection
from brevia.services import BaseService
from brevia.utilities.dates import date_filter
from brevia.utilities.json_api import query_data_pagination
from brevia.utilities.types import load_type

MAX_DURATION = 120  # default max duration is 120 min / 2hr
MAX_ATTEMPTS = 1  # default max number of attempts


class AsyncJobsStore(BaseModel):
    # pylint: disable=too-few-public-methods,not-callable
    """ Async Jobs table """
    __tablename__ = "async_jobs"

    service = Column(String(), nullable=False)
    payload = Column(JSON())
    expires = Column(TIMESTAMP(timezone=False))
    created = Column(
        TIMESTAMP(timezone=False),
        nullable=False,
        server_default=func.current_timestamp(),
    )
    completed = Column(TIMESTAMP(timezone=False))
    locked_until = Column(TIMESTAMP(timezone=False))
    max_attempts = Column(
        SMALLINT(),
        nullable=False,
        server_default='1',
    )
    result = Column(JSON(), nullable=True)


def single_job(uuid: str) -> (AsyncJobsStore | None):
    """ Get single job by UUID """
    with Session(db_connection()) as session:
        return session.get(AsyncJobsStore, uuid)


class JobsFilter(PydanticModel):
    """ Jobs filter """
    min_date: str | None = None
    max_date: str | None = None
    service: str | None = None
    completed: bool | None = None
    page: int = 1
    page_size: int = 50


def get_jobs(filter: JobsFilter) -> dict:  # pylint: disable=redefined-builtin
    """
    Read async jobs with optional filters using pagination data in response.
    """

    # Handle date filters - only apply if explicitly provided
    filter_min_date = text('1 = 1')  # always true by default
    filter_max_date = text('1 = 1')  # always true by default

    if filter.min_date:
        min_date = date_filter(filter.min_date, 'min')
        filter_min_date = AsyncJobsStore.created >= min_date

    if filter.max_date:
        max_date = date_filter(filter.max_date, 'max')
        filter_max_date = AsyncJobsStore.created <= max_date

    filter_service = text('1 = 1')  # (default) always true expression
    if filter.service:
        filter_service = AsyncJobsStore.service == filter.service
    filter_completed = text('1 = 1')  # (default) always true expression
    if filter.completed is not None:
        filter_completed = (
            AsyncJobsStore.completed.is_not(None)
            if filter.completed
            else AsyncJobsStore.completed.is_(None)
        )

    with Session(db_connection()) as session:
        query = get_jobs_query(
            session=session,
            filter_min_date=filter_min_date,
            filter_max_date=filter_max_date,
            filter_service=filter_service,
            filter_completed=filter_completed,
        )
        result = query_data_pagination(
            query=query,
            page=filter.page,
            page_size=filter.page_size
        )
        return result


def get_jobs_query(
    session: Session,
    filter_min_date: BinaryExpression,
    filter_max_date: BinaryExpression,
    filter_service: BinaryExpression,
    filter_completed: BinaryExpression,
) -> Query:
    """
    Constructs a SQLAlchemy query to retrieve async jobs based on specified filters.
    """

    query = (
        session.query(
            AsyncJobsStore.uuid,
            AsyncJobsStore.service,
            AsyncJobsStore.payload,
            AsyncJobsStore.expires,
            AsyncJobsStore.created,
            AsyncJobsStore.completed,
            AsyncJobsStore.locked_until,
            AsyncJobsStore.max_attempts,
            AsyncJobsStore.result,
        )
        .filter(filter_min_date, filter_max_date, filter_service, filter_completed)
        .order_by(desc(AsyncJobsStore.created))
    )
    return query


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
    service_class = load_type(service, BaseService)

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
        job_store.payload['job_id'] = str(job_store.uuid)
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
