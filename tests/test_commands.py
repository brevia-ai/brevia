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
    cleanup_jobs,
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


def test_cleanup_jobs_dry_run():
    """Test cleanup_jobs command with dry run"""
    from datetime import datetime, timedelta
    from brevia.async_jobs import create_job, AsyncJobsStore
    from brevia.connection import db_connection
    from sqlalchemy.orm import Session

    # Create a test job with old date
    service = 'test_cleanup_command'
    payload = {'max_duration': 10, 'max_attempts': 1}
    job = create_job(service, payload)

    # Set created date to the past
    past_date = datetime.now() - timedelta(days=2)

    with Session(db_connection()) as session:
        job_store = session.get(AsyncJobsStore, job.uuid)
        job_store.created = past_date
        session.add(job_store)
        session.commit()

    runner = CliRunner()
    cutoff_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

    # Test dry run
    result = runner.invoke(cleanup_jobs, [
        '--before-date', cutoff_date,
        '--dry-run'
    ])  # No confirmation needed for dry run

    assert result.exit_code == 0
    assert 'Dry run completed' in result.output


def test_cleanup_jobs_actual_deletion():
    """Test cleanup_jobs command with actual deletion"""
    from datetime import datetime, timedelta
    from brevia.async_jobs import create_job, single_job, AsyncJobsStore
    from brevia.connection import db_connection
    from sqlalchemy.orm import Session

    # Create test jobs
    service = 'test_cleanup_command_delete'
    payload = {'max_duration': 10, 'max_attempts': 1}
    job1 = create_job(service, payload)
    job2 = create_job(service, payload)

    # Set one job to have old date
    past_date = datetime.now() - timedelta(days=2)

    with Session(db_connection()) as session:
        job1_store = session.get(AsyncJobsStore, job1.uuid)
        job1_store.created = past_date
        session.add(job1_store)
        session.commit()

    runner = CliRunner()
    cutoff_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

    # Test actual deletion
    result = runner.invoke(cleanup_jobs, [
        '--before-date', cutoff_date,
    ], input='y\n')  # Provide 'y' input for confirmation

    assert result.exit_code == 0
    assert 'Successfully deleted' in result.output

    # Verify job1 is deleted and job2 still exists
    assert single_job(job1.uuid) is None
    assert single_job(job2.uuid) is not None


def test_cleanup_jobs_no_jobs_to_delete():
    """Test cleanup_jobs command when no jobs need to be deleted"""
    from datetime import datetime, timedelta

    runner = CliRunner()
    # Use a very old date to ensure no jobs are found
    old_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')

    result = runner.invoke(cleanup_jobs, [
        '--before-date', old_date,
    ], input='y\n')  # Provide 'y' input for confirmation

    assert result.exit_code == 0
    assert 'No async jobs to delete' in result.output


def test_cleanup_jobs_with_datetime():
    """Test cleanup_jobs command with datetime format"""
    from datetime import datetime, timedelta
    from brevia.async_jobs import create_job, single_job, AsyncJobsStore
    from brevia.connection import db_connection
    from sqlalchemy.orm import Session

    # Create a test job
    service = 'test_cleanup_datetime'
    payload = {'max_duration': 10, 'max_attempts': 1}
    job = create_job(service, payload)

    # Set created date to the past
    past_date = datetime.now() - timedelta(days=2)

    with Session(db_connection()) as session:
        job_store = session.get(AsyncJobsStore, job.uuid)
        job_store.created = past_date
        session.add(job_store)
        session.commit()

    runner = CliRunner()
    # Use full datetime format
    cutoff_datetime = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S')

    result = runner.invoke(cleanup_jobs, [
        '--before-date', cutoff_datetime,
    ], input='y\n')  # Provide 'y' input for confirmation

    assert result.exit_code == 0
    assert 'Successfully deleted' in result.output

    # Verify job is deleted
    assert single_job(job.uuid) is None


def test_cleanup_jobs_cancelled_operation():
    """Test cleanup_jobs command when user cancels the operation"""
    from datetime import datetime, timedelta
    from brevia.async_jobs import create_job, single_job, AsyncJobsStore
    from brevia.connection import db_connection
    from sqlalchemy.orm import Session

    # Create a test job
    service = 'test_cleanup_cancelled'
    payload = {'max_duration': 10, 'max_attempts': 1}
    job = create_job(service, payload)

    # Set created date to the past
    past_date = datetime.now() - timedelta(days=2)

    with Session(db_connection()) as session:
        job_store = session.get(AsyncJobsStore, job.uuid)
        job_store.created = past_date
        session.add(job_store)
        session.commit()

    runner = CliRunner()
    cutoff_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

    # Test cancelled operation (user responds 'n')
    result = runner.invoke(cleanup_jobs, [
        '--before-date', cutoff_date,
    ], input='n\n')  # User cancels the operation

    assert result.exit_code == 0
    assert 'Operation cancelled' in result.output

    # Verify job still exists
    assert single_job(job.uuid) is not None
