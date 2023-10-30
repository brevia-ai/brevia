"""Commands module tests"""
from pathlib import Path
from os import unlink
from os.path import exists
from click.testing import CliRunner
from brevia.commands import (
    db_current_cmd,
    db_upgrade_cmd,
    db_downgrade_cmd,
    export_collection,
    import_collection,
    import_file,
    run_test_service,
)
from brevia.collections import create_collection, collection_name_exists


def test_db_current_cmd():
    """ Test db_current_cmd function """
    runner = CliRunner()
    result = runner.invoke(db_current_cmd)
    assert result.exit_code == 0


def test_db_upgrade_cmd():
    """ Test db_upgrade_cmd function """
    runner = CliRunner()
    result = runner.invoke(db_upgrade_cmd)
    assert result.exit_code == 0


def test_db_downgrade_cmd():
    """ Test db_downgrade_cmd function """
    runner = CliRunner()
    result = runner.invoke(db_downgrade_cmd, ['--revision', 'base'])
    assert result.exit_code == 0


def test_export_collection():
    """ Test export_collection function """
    collection = create_collection('export-test', {})
    folder_path = f'{Path(__file__).parent}/files/'
    runner = CliRunner()
    result = runner.invoke(export_collection, [
        '--collection',
        collection.name,
        '--folder-path',
        folder_path,
    ])
    assert result.exit_code == 0
    assert exists(f'{folder_path}/{collection.name}-collection.csv')
    assert exists(f'{folder_path}/{collection.name}-embedding.csv')
    unlink(f'{folder_path}/{collection.name}-collection.csv')
    unlink(f'{folder_path}/{collection.name}-embedding.csv')


def test_import_collection():
    """ Test import_collection function """
    collection = 'test-collection'
    assert not collection_name_exists(collection)

    folder_path = f'{Path(__file__).parent}/files/'
    runner = CliRunner()
    result = runner.invoke(import_collection, [
        '--collection',
        collection,
        '--folder-path',
        folder_path,
    ])
    assert result.exit_code == 0
    assert collection_name_exists(collection)


def test_import_file():
    """ Test import_file function """
    file_path = f'{Path(__file__).parent}/files/empty.pdf'
    runner = CliRunner()
    result = runner.invoke(import_file, [
        '--collection',
        'test-collection',
        '--file-path',
        file_path,
    ])
    assert result.exit_code == 0
    assert collection_name_exists('test-collection')


def test_run_test_service():
    """ Test run_test_service function """
    file_path = f'{Path(__file__).parent}/files/run_test_service.yml'
    runner = CliRunner()
    result = runner.invoke(run_test_service, [
        '--file-path',
        file_path,
    ])
    assert result.exit_code == 0
    output_path = f'{Path(__file__).parent}/files/output-1.txt'
    assert exists(output_path)
    unlink(output_path)
