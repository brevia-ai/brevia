import pytest
from pathlib import Path
from dotenv import load_dotenv
from alembic import command
from alembic.config import Config
from brevia.index import init_index
from brevia.settings import Settings, get_settings


def pytest_sessionstart(session):
    """Init index data, just once"""
    return init_index()


def update_settings():
    """Update settings reading from `tests/.env` file"""
    load_dotenv(f'{Path(__file__).parent}/.env', override=True)
    settings = get_settings()
    new_settings = Settings(_env_file=['.env', f'{Path(__file__).parent}/.env'])
    settings.update(new_settings)


@pytest.fixture(autouse=True)
def env_vars_db():
    """Load .env inside `tests` folder"""
    update_settings()
    root_path = Path(__file__).parent.parent
    alembic_conf = Config(f'{root_path}/alembic.ini')
    command.upgrade(alembic_conf, 'head')

    yield

    command.downgrade(alembic_conf, 'base')
