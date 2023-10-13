import pytest
from pathlib import Path
from dotenv import load_dotenv
from alembic import command
from alembic.config import Config


@pytest.fixture(autouse=True)
def env_vars_db():
    """Load .env inside `tests` folder"""
    load_dotenv(f'{Path(__file__).parent}/.env', override=True)
    root_path = Path(__file__).parent.parent
    alembic_conf = Config(f'{root_path}/alembic.ini')
    command.upgrade(alembic_conf, 'head')

    yield

    command.downgrade(alembic_conf, 'base')
