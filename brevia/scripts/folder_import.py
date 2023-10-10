"""Import a folder containing PDF files performing embedding and store."""
import glob
import sys
from dotenv import load_dotenv
from brevia import index


def load_documents():
    pathname = sys.argv[1] + '/*.pdf'
    for file in glob.glob(pathname=pathname):
        print(file)
        num_docs = index.load_pdf_file(
            file_path=file,
            collection_name=sys.argv[2],
        )

        print(
            f"""
            Index collection '{sys.argv[2]}'
            updated with {num_docs} documents from {file}."""
        )


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python folder_import.py <folder_path> <collection_name>")
        sys.exit()

    load_dotenv()
    index.init_index()
    load_documents()
