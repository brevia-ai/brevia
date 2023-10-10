"""Import a CSV file performing embedding and store."""
import sys
import os
from langchain.docstore.document import Document
from langchain.document_loaders.csv_loader import CSVLoader
from dotenv import load_dotenv
from brevia import index, load_file


def load_documents(
    file_path: str,
    collection: str,
) -> list[Document]:
    """ Load documents in collection index from a CSV file """
    if not os.path.isfile(file_path):
        print(f"File {file_path} does not exist.")
        sys.exit()

    loader = CSVLoader(
        file_path=file_path,
        csv_args={
            'delimiter': ',',
            'quotechar': '"',
            'doublequote': True,
            'skipinitialspace': False,
        }
    )
    documents = loader.load()
    texts_count = 0
    for doc in documents:
        doc.page_content = load_file.cleanup_text(doc.page_content)
        texts_count += index.add_document(
            document=doc,
            collection_name=collection,
        )

    print(
        f"""Index collection '{collection}'
        updated with {len(documents)} documents and {texts_count} texts"""
    )


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python csv_import.py <csv_file_name> <collection_name>")
        sys.exit()
    load_dotenv()
    index.init_index()
    load_documents(
        file_path=sys.argv[1],
        collection=sys.argv[2]
    )
