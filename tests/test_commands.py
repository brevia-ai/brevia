"""Commands module tests"""
import glob
from pathlib import Path
from os import unlink
from os.path import exists
from click.testing import CliRunner
from langchain.docstore.document import Document
from brevia.commands import (
    db_current_cmd,
    db_upgrade_cmd,
    db_downgrade_cmd,
    db_revision_cmd,
    export_collection,
    import_collection,
    import_file,
    run_test_service,
    create_access_token,
    create_openapi,
    update_collection_links,
)
from brevia.collections import create_collection, collection_name_exists
from brevia.settings import get_settings
from brevia.index import add_document


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
    folder_path = f'{Path(__file__).parent}/files'
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

    folder_path = f'{Path(__file__).parent}/files'
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
    file_path = f'{Path(__file__).parent}/files/docs/empty.pdf'
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


def test_create_access_token():
    """ Test create_access_token function """
    settings = get_settings()
    settings.tokens_secret = 'secretsecretsecret'
    runner = CliRunner()
    result = runner.invoke(create_access_token, [
        '--user',
        'gustavo',
        '--duration',
        '10',
    ])
    assert result.exit_code == 0
    settings.tokens_secret = ''


def test_create_openapi():
    """ Test create_openapi function """
    output_path = f'{Path(__file__).parent}/files/openapi.json'
    runner = CliRunner()
    result = runner.invoke(create_openapi, [
        '--output',
        output_path,
    ])
    assert result.exit_code == 0
    assert exists(output_path)
    unlink(output_path)


def test_update_collection_links():
    """ Test update_collection_links function """
    collection = create_collection('test', {})
    doc1 = Document(page_content='some',
                    metadata={'type': 'links', 'url': 'https://example.com'})
    add_document(document=doc1, collection_name='test')
    runner = CliRunner()
    result = runner.invoke(update_collection_links, [
        '--collection',
        collection.name,
    ])
    assert result.exit_code == 0


def test_db_revision_cmd():
    """ Test db_revision_cmd function """
    runner = CliRunner()
    result = runner.invoke(db_revision_cmd, [
        '--message',
        'Test revision message',
    ])
    assert result.exit_code == 0
    assert 'New revision created: Test revision message' in result.output

    # Clean up generated migration files
    versions_dir = f'{Path(__file__).parent.parent}/brevia/alembic/versions'
    migration_files = glob.glob(f'{versions_dir}/*_test_revision_message.py')
    for file_path in migration_files:
        if exists(file_path):
            unlink(file_path)


def test_db_revision_cmd_with_autogenerate():
    """ Test db_revision_cmd function with autogenerate flag """
    runner = CliRunner()
    result = runner.invoke(db_revision_cmd, [
        '--message',
        'Test autogenerate revision',
        '--autogenerate',
    ])
    assert result.exit_code == 0
    assert 'New revision created: Test autogenerate revision' in result.output

    # Clean up generated migration files
    versions_dir = f'{Path(__file__).parent.parent}/brevia/alembic/versions'
    migration_files = glob.glob(f'{versions_dir}/*_test_autogenerate_revision.py')
    for file_path in migration_files:
        if exists(file_path):
            unlink(file_path)
