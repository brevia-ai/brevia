"""Configure settings and fixtures to be used in unit tests"""
from pathlib import Path
import os
import pytest
from alembic import command
from alembic.config import Config
from dotenv import dotenv_values
from brevia.settings import Settings, get_settings
from brevia.index import init_splitting_data
import brevia.alembic


def pytest_sessionstart(session):
    """Init index data, just once"""
    return init_splitting_data()


def pytest_configure():
    """Avoid .env (dotenv) and env vars usage in settings for unit tests"""
    Settings.model_config['env_file'] = None
    # make sure we don't have any env var set
    for key in Settings.model_fields:
        os.environ.pop(key.upper(), None)


def update_settings():
    """Update settings reading from `tests/.env` file"""
    new_settings = dotenv_values(dotenv_path=f'{Path(__file__).parent}/.env')
    new_settings = {k.lower(): v for k, v in new_settings.items()}
    test_settings = Settings(**new_settings)
    test_settings.update_from_db()
    settings = get_settings()
    settings.update(test_settings)
    settings.setup_environment()
    # Force tokens and test models vars
    settings.tokens_secret = ''
    settings.tokens_users = ''
    settings.status_token = ''
    settings.use_test_models = True
    settings.file_output_base_path = f'{Path(__file__).parent}/files'


@pytest.fixture(autouse=True)
def env_vars_db():
    """Load .env inside `tests` folder"""
    update_settings()
    root_path = Path(__file__).parent.parent
    alembic_conf = Config(f'{root_path}/alembic.ini')
    script_location = os.path.dirname(brevia.alembic.__file__)
    alembic_conf.set_main_option('script_location', script_location)
    command.upgrade(alembic_conf, 'head')

    yield

    command.downgrade(alembic_conf, 'base')
