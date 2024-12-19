"""DB migrations commands """
from os import getcwd
from os.path import dirname
from alembic.config import Config
from alembic import command

alembic_cfg = Config(f'{getcwd()}/alembic.ini')
alembic_cfg.set_main_option('script_location', dirname(__file__))


def current(verbose=False):
    command.current(alembic_cfg, verbose=verbose)


def upgrade(revision="head"):
    command.upgrade(alembic_cfg, revision)


def downgrade(revision):
    command.downgrade(alembic_cfg, revision)
