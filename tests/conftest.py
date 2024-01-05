import pytest
from pathlib import Path
from alembic import command
from alembic.config import Config
from brevia.index import init_index
from brevia.settings import Settings, get_settings


def pytest_sessionstart(session):
    """Init index data, just once"""
    return init_index()


def update_settings():
    """Update settings reading from `tests/.env` file"""
    new_settings = Settings(_env_file=['.env', f'{Path(__file__).parent}/.env'])
    settings = get_settings()
    settings.update(new_settings)
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
