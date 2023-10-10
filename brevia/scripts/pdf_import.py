"""Import a PDF file performing embedding and store."""
import sys
from dotenv import load_dotenv
from brevia import index


def load_documents():
    """Load documents from PDF using command line args"""
    load_dotenv()
    index.init_index()
    num_docs = index.load_pdf_file(
        file_path=sys.argv[1],
        collection_name=sys.argv[2],
        page_from=None if len(sys.argv) < 4 else int(sys.argv[3]),
        page_to=None if len(sys.argv) < 5 else int(sys.argv[4]),
    )

    print(
        f"""
        Index collection '{sys.argv[2]}'
        updated with {num_docs} documents."""
    )


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python pdf_import.py <pdf_file_name> "
              "<collection_name> [page_from] [page_to]")
        sys.exit()
    load_documents()
