"""Import a collection from CSV postgres files."""
import sys
from os import path
from dotenv import load_dotenv
from brevia import connection, collections


def import_collection_data(
    folder_path: str,
    collection: str,
):
    """Import collection data using `psql`"""
    if collections.collection_name_exists(collection):
        print(f"Collection '{collection}' already exists, exiting")
        sys.exit(1)

    csv_file_collection = f"{folder_path}/{collection}-collection.csv"
    csv_file_embedding = f"{folder_path}/{collection}-embedding.csv"
    print(f"Importing from {csv_file_collection} and {csv_file_embedding}")
    if not path.exists(csv_file_collection):
        print(f"CSV file {csv_file_collection} not found, exiting...")
        return
    if not path.exists(csv_file_embedding):
        print(f"CSV file {csv_file_embedding} not found, exiting...")
        return

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


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python import_collection.py <folder_path> <collection_name>")
        sys.exit(1)
    load_dotenv()
    import_collection_data(
        folder_path=sys.argv[1],
        collection=sys.argv[2],
    )
