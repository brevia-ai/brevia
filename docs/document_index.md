# Indexing Documents

This section documents the endpoints for managing vector indexing of documents within a RAG system.
Vector indexing enables efficient retrieval of relevant documents based on semantic similarity.

The Brevia library provides a powerful and efficient solution for indexing documents in a RAG system. It leverages the capabilities of the NLTK library for intelligent chunking of long documents, preserving paragraph structure.
Additionally, Brevia seamlessly integrates with an OCR tool to extract text from image-rich PDFs, ensuring comprehensive indexing of all document types.

## Key Features:

**Intelligent Chunking**: Brevia utilizes NLTK's advanced algorithms to divide lengthy documents into smaller, manageable chunks while maintaining paragraph boundaries. This approach optimizes the indexing process and enhances the accuracy of vector representations.

**OCR Integration**: Brevia seamlessly integrates with an OCR tool, enabling efficient text extraction from PDFs containing images or scanned content. This expands the scope of document indexing to include a wider range of document formats.

**Efficient Indexing**: Brevia's optimized indexing process ensures fast and efficient vectorization of documents, enabling rapid retrieval and analysis of relevant information.

## Configuration

Make sure to create a `.env` file in your project directory and include the following variables. (see [configuration](config.md))

### Embeddings

This variable specifies the type of embedding model used to convert text documents into numerical vectors. In this case, it's set to `openai-embeddings`, indicating that you'll be using OpenAI's embedding service.

`EMBEDDINGS='{"_type": "openai-embeddings"}'`

Other services supported are `cohere-embeddings`

### Text Segmentation
`TEXT_CHUNK_SIZE`
This variable controls the maximum size of individual text chunks during processing. Large documents are split into smaller segments for efficient handling by the embedding model.

Default Value: 2000 (token)

Adjust this value based on your document sizes and hardware resources. Larger chunks typically yield more accurate embeddings, but require more memory. Experiment to find the optimal balance for your setup.

`TEXT_CHUNK_OVERLAP`
This variable specifies the amount of overlap between consecutive text chunks. Overlap ensures continuity within the document and helps capture contextual information across sections.

Default Value: 100 (token)

Increase the overlap for documents with important cross-sectional references, but reduce it for faster processing of independent sections.
Consider experimenting with different values based on your document characteristics.

example:
```bash
TEXT_CHUNK_SIZE=2000
TEXT_CHUNK_OVERLAP=100
```

> **Note**: Remember to restart your application after modifying these environment variables for the changes to take effect.

## Endpoints

### POST `/index`

Splits the text and creates new vectors index and a list of embeddings for a document.

Payload:
```JSON
{
  "content": "Your document text or PDF file path",
  "collection_id": "{{collection_id}}",
  "document_id": "{{document_id}}",
  "metadata": {"category": "cat1", ...} // Optional
}
```

### POST `/index/upload`

Indexes a PDF document by uploading it.

Payload (JavaScript example):
```JavaScript
const formdata = new FormData();
formdata.append("file", fileInput.files[0], "path/to/your/file.pdf");
formdata.append("collection_id", "45260e10-53f5-48c7-98e7-462141e65311");
formdata.append("document_id", "2");
formdata.append("metadata", "{\"type\": \"files\", \"file\": \"test.pdf\"}");
```

### POST `/index/metadata`

Updates metadata for an existing document.

Payload:
```JSON
{
  "collection_id": "{{collection_id}}",
  "document_id": "{{document_id}}",
  "metadata": {"integration": "true", "category": "regolamento", ...}
}
```

### GET `/index/{collection_id}`

Returns a paginated list of documents indexed in a collection; each item corresponds to a pg_embeddings record, so you can get usually more items for the same document

### GET `/index/{{collection_id}}/{{document_id}}`

Retrieves information about an indexed document.

### GET `/index/{collection_id}/index_metadata`

Returns a list of documents metadata in a collection, so you will get unique items with cmetadata and custom_id (alias for document id in brevia)

### DELETE `/index/{{collection_id}}/{{document_id}}`

Deletes an indexed document.

## Example Usage (Python) ?
