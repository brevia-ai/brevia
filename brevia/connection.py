""" DB connection utility functions """
import subprocess
from functools import lru_cache
import sys
from sqlalchemy import create_engine
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session
from sqlalchemy.exc import DatabaseError
from langchain_community.vectorstores.pgembedding import CollectionStore
from brevia.settings import get_settings


def connection_string() -> str:
    """ Postgres+pgvector db connection string """
    return get_settings().connection_string()


@lru_cache
def get_engine():
    """Return db engine (using lru_cache)"""
    return create_engine(
            connection_string(),
            pool_size=get_settings().pgvector_pool_size,
        )


def db_connection() -> Connection:
    """ SQLAlchemy db connection """
    return get_engine().connect()


def test_connection() -> bool:
    """ Test db connection with a simple query """
    try:
        with Session(db_connection()) as session:
            (
                session.query(CollectionStore.uuid)
                .limit(1)
                .all()
            )
        return True
    except DatabaseError:
        print('Error performing a simple SQL query', file=sys.stderr)
        return False


def psql_command(
    cmd: str,
) -> bool:
    """Perform command on db using `psql`"""
    conf = get_settings()
    host = conf.pgvector_host
    port = conf.pgvector_port
    database = conf.pgvector_database
    user = conf.pgvector_user
    password = conf.pgvector_password

    cmd = ['psql', '-U', user, '-h', host, '-p', f'{port}', '-c', cmd, database]

    with subprocess.Popen(
        cmd,
        env={'PGPASSWORD': password},
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE
    ) as proc:
        res = proc.communicate()
        output = res[0].decode('UTF-8')
        print(f"psql output: {output}")
        if proc.returncode != 0:
            print('Error launching psql command', file=sys.stderr)
            return False

    print('Psql command executed successfully')
    return True
