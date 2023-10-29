"""Utility commands for applications"""
import json
import click
from dotenv import load_dotenv
from brevia.alembic import current, upgrade, downgrade
from brevia.utilities import files_import


@click.command()
@click.option("-v", "--verbose", is_flag=True, default=False, help="Verbose mode")
def db_current_cmd(verbose):
    """Display current database revision"""
    load_dotenv()
    current(verbose)


@click.command()
@click.option("-r", "--revision", default="head", help="Revision target")
def db_upgrade_cmd(revision):
    """Upgrade to a later database revision"""
    load_dotenv()
    upgrade(revision)


@click.command()
@click.option("-r", "--revision", required=True, help="Revision target")
def db_downgrade_cmd(revision):
    """Revert to a previous database revision"""
    load_dotenv()
    downgrade(revision)


@click.command()
@click.option("-f", "--file", required=True, help="File or folder path")
@click.option("-c", "--collection", required=True, help="Collection name")
@click.option("-o", "--options", required=True, help="Loader options in JSON format")
def import_file(file_path: str, collection: str, options: str = ''):
    """Add file or folder content to collection"""
    load_dotenv()
    # pass loader options via JSON string
    kwargs = {} if not options else json.loads(options)
    num = files_import.index_file_folder(
        file_path=file_path,
        collection=collection,
        **kwargs
    )
    print(
        f"""Collection '{collection}'
        updated from '{file_path}' with {num} documents."""
    )
