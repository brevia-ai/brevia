# Endpoints

### POST `/chat`

Initiates a natural conversation with the model.

**Payloads**:

`question`: The query you want to ask the model.
`collection`: The collection of documents to search for relevant information.

```JSON
{
  "question": "{{query}}",
  "collection": "{{collection}}"
}
```

Same as the simple body, plus:
`chat_history`: An array of previous questions and answers to provide context for the current query.

```JSON
{
    "question": "{{query}}",
    "collection": "{{collection}}",
    "chat_history": [
        {
            "query": "what is artificial intelligence?",
            "answer": "Artificial intelligence (AI) refers to the simulation or approximation of human intelligence in machines. The goals of artificial intelligence include computer-enhanced learning, reasoning, and perception"
        },
        {
            "query": "Is AI good or bad?",
            "answer": "These technologies not only save time, but also potentially save lives by minimizing human error and ensuring a safer working environment. In addition, automating repetitive tasks in design, planning, and management with AI frees up human workers to focus on more complex and creative aspects."
        }
    ]
}
```

### POST `/completion`

Executes a single command or request without conversational context.

**Paylodas**:

`text`: The text you want to process or transform.
`prompt`: A custom instruction defining how to process the text.
`token_data`: (Optional) Set to true to return token-level data like part-of-speech tags.

```JSON
{
    "text": "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum",
    "prompt": {
        "_type": "prompt",
        "input_variables": [
            "text"
        ],
        "template": "formatta il seguente testo in formato EMAIL :\n\n{text}\n\n SCRIVI L'EMAIL:"
    },
    "token_data": true
}
```

### GET `/chat_history`

### GET `/chat_history?max_date=2023-04-20&collection={{collection}}&page=1&page_size=20`

Retrieves past conversation history.

**Optional Parameters**:

`max_date`: Filter history entries by date.
`collection`: Filter history entries by collection.
`page`: Paginate through large history datasets.
`page_size`: Control the number of entries per page.

### POST `/search`

Searches for relevant documents based on a query.

Payloads:

`query`: The search query.
`collection`: The collection of documents to search.

```JSON
{
    "query": "{{query}}",
    "collection": "{{collection}}"
}
```

**Additional Parameters**:

`docs_num`: Specify the number of documents to return.
`distance_strategy_name`: Choose the algorithm for measuring document similarity.

```JSON
{
    "query": "{{query}}",
    "collection": "{{collection}}",
    "docs_num": 6,
    "distance_strategy_name": "euclidean"
}
```

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

### GET `/status`

Retrieve API status, check if database is up and running.
If everything works as expected we get a `200 OK` status code and a response like:

```JSON
{
    "db_status": "OK",
}
```

If, for instance, there is an issue with the database connection or performing simple queries we get a `503 Service Unavailable` status code with this response:

```JSON
{
    "db_status": "KO",
}
```
