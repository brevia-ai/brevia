# Collections

## Overview

Collections are a fundamental component of a RAG system, serving as containers for storing and managing documents.
The Brevia library provides a robust and flexible framework for working with collections, enabling efficient indexing, querying, and retrieval of documents.

## Key Features:

**Flexible Data Model**: BrevIA utilizes a JSON-based metadata schema, allowing for flexible storage of collection-specific information and document-level metadata.
This schema can be easily extended to accommodate custom requirements.

**Powerful Indexing**: Documents within a collection are indexed using vector representations, facilitating efficient and accurate retrieval based on semantic similarity.

**Intuitive API**: Brevia provides a comprehensive API for managing collections, including creation, retrieval, modification, and deletion.

## Collections in Brevia

Each collection in Brevia is represented by two tables in the underlying database:

`langchain_pg_collection`: Stores general collection information, including its name, creation timestamp, and metadata.

`langchain_pg_embeddings`: Contains the vector representations for all documents within the collection.
The cmetadata field in both tables plays a crucial role, allowing for the storage of various types of information:

*Collection-level metadata*: This can include general information about the collection, such as its purpose, creator, or creation date.

*Document-level metadata*: This can include specific details about each document, such as its author, title, publication date, or any custom attributes relevant to the application.

## Collection Management API

Brevia provides a RESTful API for managing collections, empowering developers to perform CRUD operations and access collection information programmatically.

### Endpoints:

`GET /collections`
Retrieves a list of all existing collections.

`GET /collections?name={{collection_name}}`
Retrieves a specific collection by its name.

`GET /collections/{{collection_id}}`
Retrieves a specific collection by its ID.

`POST /collections`
Creates a new collection.

**Example:**

```JSON
{
  "name": "test_collection",
  "cmetadata": {
    "note": "Sample collection for testing purposes",
    "description": "This collection contains documents related to AI and NLP"
  }
}
```

`PATCH /collections/{{collection_id}}`
Updates an existing collection.

**Example:**

```JSON
{
  "name": "updated_collection",
  "cmetadata": {
    "note": "Updated collection metadata",
    "description": "This collection now includes additional information about documents",
    "documents_metadata": {
      "$schema": "http://json-schema.org/draft-06/schema#",
      "type": "object",
      "properties": {
        "valid_from": {
          "type": "string",
          "format": "date",
          "description": "Document validity start date"
        },
        "valid_to": {
          "type": "string",
          "format": "date",
          "description": "Document validity end date"
        },
        "integration": {
          "type": "boolean",
          "description": "Integration flag"
        },
        "category": {
          "type": "string",
          "description": "Document category",
          "enum": ["cat1", "cat2", "cat3"]
        }
      }
    }
  }
}
```


In this example, we update the collection metadata to include additional information about the documents, such as their validity period, integration status, and category.

`DELETE /collections/{{collection_id}}`
Deletes a collection.

## Further Resources

Indexing: link to indexing documentation
Database: link to database documentation
