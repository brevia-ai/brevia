"""DB migrations commands """
from os import getcwd

from alembic.config import Config
from alembic import command


ALEMBIC_CFG = Config(f'{getcwd()}/alembic.ini')


def current(verbose=False):
    command.current(ALEMBIC_CFG, verbose=verbose)


def upgrade(revision="head"):
    command.upgrade(ALEMBIC_CFG, revision)


def downgrade(revision):
    command.downgrade(ALEMBIC_CFG, revision)
