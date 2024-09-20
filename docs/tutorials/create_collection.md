# Setting Up a RAG System with Brevia Library

This tutorial describes how to set up the simplest Retrieval-Augmented Generation (RAG) system using the Brevia library.
The default RAG system in Brevia includes:

- Conversational memory system, with a simple parameterized topic identification system.
- Integrated OCR in the indexing of PDF documents.
- Textsplitter using NTKL for coherent text segmentation.

## Prerequisites

Please refer to the [Setup](../setup.md) and [Configuration](../config.md) pages in the documentation for setup and base configuration the environment and database.

## Configurations

### RAG

This JSON snippets provides configuration settings for basic RAG functionalities.
Two main components are defined:

**Completion**:
Represents natural conversation, generating comprehensive responses to user queries.

**Follow-up**:
Involves rewriting the question based on chat history, ensuring contextual coherence.

```JSON
QA_COMPLETION_LLM='{
    "_type": "your_llm_type",
    "model_name": "your_llm_model",
    "temperature": 0.7,
    "max_tokens": 1000
}'

QA_FOLLOWUP_LLM='{
    "_type": "your_llm_type",
    "model_name": "your_llm_model",
    "temperature": 0.7,
    "max_tokens": 200
}'
```

Replace `your_llm_type` and `your_llm_model` with your chosen LLM provider and specific model (e.g., "openai-chat", "gpt-4o-mini").
Adjust `temperature` and `max_tokens` parameters as needed.

## Database

### Docker Compose

Run docker compose to spin up a PostgreSQL database with pg_vector.

```bash
docker compose up
```

### pgAdmin Integration

Run docker compose --profile admin up to launch both Postgres+pgvector and pgAdmin container.
Access pgAdmin in your browser at http://localhost:4000 (port configurable in .env file).

```bash
docker compose --profile admin up
```

### Migrations

Run db_upgrade (using [Alembic](https://alembic.sqlalchemy.org)) to create or update the database schema.

```bash
db_upgrade
```

## Launch API Server

You are now ready to go, simply run

```bash
uvicorn --env-file .env main:app`
```

## Create a new Collection

Use the `/collections` API endpoint with a **POST** request and the following payload:

```JSON
{
  "name": "your_collection_name",
  "cmetadata": {
    "note": "Your collection description",
    "description": "More detailed description of your collection"
  }
}
```

> **Note**: Replace `your_collection_name` with your desired name and update the descriptions as needed.

## Index Your Documents

Once the collection is created, it is necessary to input the set of documents that will constitute the knowledge base of our RAG system. With Brevia, it is possible to perform indexing on both free-text and files containing text or images. The textual content is vectorized using the reference model's endpoints and inserted into the collection.
Supported file formats include *txt*, *pdf* (including images, through *OCR*).

> **Note**: Through the .env file, it is possible to parameterize the chunk size and overlap, see [configuration](../config.md).

### Text Content:

Use the `/index` endpoint with a **POST** request and the following payload:

```JSON
{
  "content": "Your text content here",
  "collection_id": "{{collection_id}}",
  "document_id": "{{document_id}}",
  "metadata": {
    "category": "your_category_name"
  }
}
```

>Note: You will need to replace placeholder values like `{{collection_id}}` with your specific information based on your setup.

### PDF Files:

Use the `/index/upload` endpoint with a **POST** request and form data (example using JavaScript):

```Javascript
const data = new FormData();
data.append('file', fs.createReadStream('/path/to/your/pdf.pdf'));
data.append('collection_id', '{{collection_id}}');
data.append('document_id', '2');
data.append('metadata', '{"type": "files", "file": "test.pdf"}');
```

> Note: Brevia uses OCR to extract text from images within PDFs.

## Query Your RAG System

Use the `/chat` endpoint with a POST request and the following payload:

```JSON
{
  "question": "Your question here",
  "collection": "{{collection_name}}"
}
```

> **Note**: Replace placeholders with your values. Refer to the Brevia documentation for additional parameters like source_docs and docs_num to control output details.

**Congratulations!**
You have successfully set up a basic RAG system using Brevia.
Remember to adjust settings and explore advanced features according to your specific needs and the Brevia documentation.
