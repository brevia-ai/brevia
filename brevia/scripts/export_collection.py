"""Export a collection to CSV postgres files."""
import sys
from os import path
from dotenv import load_dotenv
from brevia import connection, collections


def export_collection_data(
    folder_path: str,
    collection: str,
):
    """Export collection data using `psql`"""
    if not collections.collection_name_exists(collection):
        print(f"Collection '{collection}' was not found, exiting")
        sys.exit(1)

    csv_file_collection = f"{folder_path}/{collection}-collection.csv"
    csv_file_embedding = f"{folder_path}/{collection}-embedding.csv"
    if path.exists(csv_file_collection):
        print(f"CSV file {csv_file_collection} exists, exiting...")
        return
    if path.exists(csv_file_embedding):
        print(f"CSV file {csv_file_embedding} exists, exiting...")
        return

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


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python export_collection.py <folder_path> <collection_name>")
        sys.exit(1)
    load_dotenv()
    export_collection_data(
        folder_path=sys.argv[1],
        collection=sys.argv[2],
    )
