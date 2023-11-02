"""Utility commands for applications"""
import json
import sys
from os import getcwd, path
from logging import config
import click
from dotenv import load_dotenv
from brevia.alembic import current, upgrade, downgrade
from brevia.utilities import files_import, run_service, collections_io
from brevia.tokens import create_token


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
@click.option("-f", "--file-path", required=True, help="File or folder path")
@click.option("-c", "--collection", required=True, help="Collection name")
@click.option("-o", "--options", required=False, help="Loader options in JSON format")
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


# A `test_service.yml` in the root folder is needed.
# `service` and `payload` keys are required with this structure:
#
# service: my_module.MyService
# output_path: path/to/output.txt
# payload:
#   file_path: /path/to/file
#   param1: value1
#   param2: value2

@click.command()
@click.option("-n", "--num", default=1, help="Number of attempts")
@click.option(
    "-f",
    "--file-path",
    default=f'{getcwd()}/test_service.yml',
    help="yaml file path"
)
def run_test_service(num: int = 1, file_path: str = f'{getcwd()}/test_service.yml'):
    """Service test"""
    load_dotenv()
    # allow module import from current working directory
    sys.path.append(getcwd())
    # initialize logging from optional log.ini
    log_ini_path = f'{getcwd()}/log.ini'
    if path.exists(log_ini_path):
        config.fileConfig(log_ini_path)

    run_service.run_service_from_yaml(file_path=file_path, num_attempts=num)


@click.command()
@click.option("-c", "--collection", required=True, help="Collection name")
@click.option(
    "-f",
    "--folder-path",
    required=True,
    help="Folder output path"
)
def export_collection(folder_path: str, collection: str):
    """Export a collection to CSV postgres files."""
    load_dotenv()
    collections_io.export_collection_data(
        folder_path=folder_path,
        collection=collection
    )


@click.command()
@click.option("-c", "--collection", required=True, help="Collection name")
@click.option(
    "-f",
    "--folder-path",
    required=True,
    help="Folder input path"
)
def import_collection(folder_path: str, collection: str):
    """Import a collection from a CSV postgres files."""
    load_dotenv()
    collections_io.import_collection_data(
        folder_path=folder_path,
        collection=collection
    )


@click.command()
@click.option("-u", "--user", default="brevia", help="Token user name")
@click.option("-d", "--duration", default=60, help="Token duration in minutes")
def create_access_token(user: str, duration: int):
    """Create an access token """
    load_dotenv()
    token = create_token(user=user, duration=duration)
    print(token)
