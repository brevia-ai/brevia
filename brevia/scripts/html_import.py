"""Import an HTML file performing embedding and store."""
import sys
import os
from langchain.docstore.document import Document
from langchain.document_loaders import BSHTMLLoader
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

    loader = BSHTMLLoader(file_path=file_path)
    documents = loader.load()

    # uncomment to use custom parsing instead of plain HTML loader
    # documents = read_html(
    #     file_path=file_path,
    #     bs_kwargs={'features': 'html.parser'},
    # )
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


# def read_html(
#     file_path: str,
#     bs_kwargs: dict = None,
# ):
#     """ Read HTML file and create documents with custom parsing """
#     from bs4 import BeautifulSoup

#     with open(file_path, 'r') as f:
#         soup = BeautifulSoup(f, **bs_kwargs)

#     meta = {'source': os.path.basename(file_path)}
#     items = soup.find_all('div', {'class': 'faq-entry-container'})
#     docs = []
#     for item in items:
#         doc = Document(page_content=item.get_text(strip=True), metadata=meta)
#         docs.append(doc)

#     return docs


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python html_import.py <html_file> <collection>")
        sys.exit()
    load_dotenv()
    index.init_index()
    load_documents(
        file_path=sys.argv[1],
        collection=sys.argv[2]
    )
