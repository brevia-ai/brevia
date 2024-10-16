"""Configure settings and fixtures to be used in unit tests"""
from pathlib import Path
import pytest
from alembic import command
from alembic.config import Config
from dotenv import dotenv_values
from brevia.index import init_splitting_data
from brevia.settings import get_settings


def pytest_sessionstart(session):
    """Init index data, just once"""
    return init_splitting_data()


def update_settings():
    """Update settings reading from `tests/.env` file"""
    new_settings = dotenv_values(dotenv_path=f'{Path(__file__).parent}/.env')
    settings = get_settings()
    settings.update(new_settings)
    settings.setup_environment()
    # Force tokens and test models vars
    settings.tokens_secret = ''
    settings.tokens_users = ''
    settings.status_token = ''
    settings.use_test_models = True


@pytest.fixture(autouse=True)
def env_vars_db():
    """Load .env inside `tests` folder"""
    update_settings()
    root_path = Path(__file__).parent.parent
    alembic_conf = Config(f'{root_path}/alembic.ini')
    command.upgrade(alembic_conf, 'head')

    yield

    command.downgrade(alembic_conf, 'base')
