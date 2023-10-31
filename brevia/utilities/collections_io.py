"""Utility functions to import/export collections using CSV postgres files."""
from os import path
from brevia import connection, collections


def export_collection_data(
    folder_path: str,
    collection: str,
):
    """Export collection data using `psql`"""
    if not collections.collection_name_exists(collection):
        raise ValueError(f"Collection '{collection}' was not found")

    csv_file_collection = f"{folder_path}/{collection}-collection.csv"
    csv_file_embedding = f"{folder_path}/{collection}-embedding.csv"
    if path.exists(csv_file_collection):
        raise ValueError(f"CSV file {csv_file_collection} already exists, exiting")
    if path.exists(csv_file_embedding):
        raise ValueError(f"CSV file {csv_file_embedding} already exists, exiting")

    select = f"SELECT * FROM langchain_pg_collection WHERE name = '{collection}'"
    copy = f"\\copy ({select}) TO '{csv_file_collection}' WITH DELIMITER ',' CSV HEADER"
    res = connection.psql_command(cmd=copy)
    if not res:
        return

    print(f"Collection record '{collection}' exported to '{csv_file_collection}'")

    sub = f"SELECT uuid from langchain_pg_collection WHERE name = '{collection}'"
    select = f"SELECT * FROM langchain_pg_embedding WHERE collection_id = ({sub})"
    copy = f"\\copy ({select}) TO '{csv_file_embedding}' WITH DELIMITER ',' CSV HEADER"
    res = connection.psql_command(cmd=copy)
    if not res:
        return

    print(f"Collection embedding for '{collection}' exported to '{csv_file_embedding}'")


def import_collection_data(
    folder_path: str,
    collection: str,
):
    """Import collection data using `psql`"""
    if collections.collection_name_exists(collection):
        raise ValueError(f"Collection '{collection}' already exists, exiting")

    csv_file_collection = f"{folder_path}/{collection}-collection.csv"
    csv_file_embedding = f"{folder_path}/{collection}-embedding.csv"
    print(f"Importing from {csv_file_collection} and {csv_file_embedding}")
    if not path.exists(csv_file_collection):
        raise ValueError(f"CSV file {csv_file_collection} not found, exiting")
    if not path.exists(csv_file_embedding):
        raise ValueError(f"CSV file {csv_file_embedding} not found, exiting")

    table = 'langchain_pg_collection'
    copy = f"\\copy {table} FROM '{csv_file_collection}' WITH DELIMITER ',' CSV HEADER"
    res = connection.psql_command(cmd=copy)
    if not res:
        return

    table = 'langchain_pg_embedding'
    copy = f"\\copy {table} FROM '{csv_file_embedding}' WITH DELIMITER ',' CSV HEADER"
    res = connection.psql_command(cmd=copy)
    if not res:
        return

    print(f"Collection '{collection}' imported")
