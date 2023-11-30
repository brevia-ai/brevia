""" DB connection utility functions """
import subprocess
import sys
from urllib import parse
import sqlalchemy
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError
from langchain.vectorstores._pgvector_data_models import CollectionStore
from brevia.settings import get_settings


def connection_string() -> str:
    """ Postgres+pgvector db connection string """
    conf = get_settings()
    driver = conf.pgvector_driver
    host = conf.pgvector_host
    port = conf.pgvector_port
    database = conf.pgvector_database
    user = conf.pgvector_user
    password = parse.quote_plus(conf.pgvector_password)

    return f"postgresql+{driver}://{user}:{password}@{host}:{port}/{database}"


def db_connection() -> sqlalchemy.engine.Connection:
    """ SQLAlchemy db connection """
    engine = sqlalchemy.create_engine(
        connection_string(),
        pool_size=get_settings().pgvector_pool_size,
    )
    return engine.connect()


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
    except OperationalError:
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
