# Endpoints

## Chat and search endpoints

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

**Optional Parameters**:

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

`source_docs`: Set to true to return source documents.
`docs_num`: Specify the number of documents to return.
`token_data`: Set to true to return token-level data like part-of-speech tags.
`multiquery`: Set to true to use MultiQueryRetriever from langchain.

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

## Collections endpoints

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

## Index endpoints

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

## Analysis endpoints

### POST `/summarize`

Performs summarization of a text passed as input

Example payload:

```JSON
{
  "text": "Lorem ipsum.......",
}
```

Additional optional payload attributes:

* `chain_type`: can be `map_reduce
* `initial_prompt`: object describing the initial prompt used on the first text chunk
* `iteration_prompt`: object describing the iteration prompt used after first text chunk
* `token_data`: flag to return token usage data

### POST `/upload_summarize`

Performs summarization of a file.

It works only with `form-data` input that must include a `file` parameter with the uploaded file and as optional parameters `chain_type` (as string, see above), `initial_prompt` and `iteration_prompt` (as JSON strings, see above), `token_data` (see above, as string with 'true' or 'false' as values)

### POST `/upload_analyze`

Performs a generic custom document analysis of a file

It works only with `form-data` input that must include a `file` parameter with the uploaded file and as optional parameters:

* `service`: string with service class name to use to perform the analysys in dot notation format
* `payload`: additional input parameters as JSON string

## Async jobs endpoints

### GET `/jobs/{uuid}`

Retrieve aync job data using its `uuid`

**Example response:**

```JSON
{
    "service": "brevia.services.SummarizeFileService",
    "created": "2024-02-29T16:31:25.546740",
    "locked_until": "2024-02-29T19:31:25",
    "result": {
        "output": "Lorem ipsum....",
    },
    "expires": "2024-02-29T21:31:25",
    "payload": {
        "file_path": "/tmp/tmpgns0ci85.pdf",
        "chain_type": "",
        "iteration_prompt": null,
        "token_data": false
    },
    "completed": "2024-02-29T17:31:27.700342",
    "max_attempts": 1,
    "uuid": "00b9118c-6bb5-4b87-968c-3b2c1b6fe3fb"
}
```

## Status endpoints

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

## Configuration endpoints

### GET `/config`

Retrieve current global configuration. A JSON object with configuration keys and value pairs is returned.
A small example excerpt could look like this (there are many more items):

```JSON
{
    "verbose_mode": true,
    "text_chunk_size": 4555,
    "text_chunk_overlap": 550,
    "search_docs_num": 7,
    "qa_completion_llm": {...}
    ...
}
```

Using a `key` query parameter you may filter only specific keys.
For instance calling `GET /config?key=text_chunk_size&key=search_docs_num` with the configuration above will result in:

```JSON
{
    "text_chunk_size": 4555,
    "search_docs_num": 7
}
```

### GET `/config/schema`

Get the configuration JSON Schema A JSON object with configuration keys and value pairs is returned.
Here is a short sample excerpt, there are many more properties:

```JSON
{
    "description": "Brevia settings",
    "properties": {
        "verbose_mode": {
            "default": true,
            "title": "Verbose Mode",
            "type": "boolean"
        },
        "text_chunk_size": {
            "default": 4000,
            "title": "Text Chunk Size",
            "type": "integer"
        },
    }
}
```

### POST `/config`

Update some configuration settings with key/value pairs. The new settings will be saved in the database and will override the corresponding default settings.

Only the submitted items will be changed, other configuration settings will not change.

But there are some limitations: some parameters such as the DB connection or security tokens cannot be changed.

Example payload:

```JSON
{
    "text_chunk_size": 4500,
    "text_chunk_overlap": 550,
    "search_docs_num": 8
}
```

### POST `/config/reset`

Reset some configuration settings to default values.
These settings will be removed from the database, if previously customized.

Only the submitted items will be reset, other configuration settings will not change.

Example payload:

```JSON
[
    "text_chunk_size",
    "text_chunk_overlap",
    "search_docs_num"
]
```

## Providers endpoints

### GET `/providers`

Retrieve a list of all available providers with their models.

A JSON objects list with provider names and their models is returned.
A small example excerpt could look like this (there are usually many more items):

```JSON
[
    {
        "model_provider": "openai",
        "models": [
            {
                "name": "gpt-4.5-preview"
            },
            {
                "name": "o1-mini"
            },
            {
                "name": "gpt-4"
            },
            {
                "name": "o3-mini"
            },
            {
                "name": "gpt-4o"
            },
            {
                "name": "gpt-4o-mini"
            }
        ]
    },
    {
        "model_provider": "cohere",
        "models": [
            {
                "name": "command-r",
                "tokens_limit": 128000
            },
            {
                "name": "command-r-plus",
                "tokens_limit": 128000
            }
        ]
    },
    {
        "model_provider": "anthropic",
        "models": [
            {
                "name": "claude-3-7-sonnet-20250219"
            },
            {
                "name": "claude-3-5-sonnet-20241022"
            }
        ]
    },
    {
        "model_provider": "ollama",
        "models": [
            {
                "name": "llama3.2:latest"
            }
        ]
    },
    {
        "model_provider": "deepseek",
        "models": [
            {
                "name": "deepseek-chat"
            },
            {
                "name": "deepseek-reasoner"
            }
        ]
    }
]
```

A boolean query parameter `list_models`, with a defaults value `true`, can be used to simply list providers without models.
Calling `GET /providers?list_models=false` will return as result:

```JSON
[
    {
        "model_provider": "openai"
    },
    {
        "model_provider": "cohere"
    },
    {
        "model_provider": "anthropic"
    },
    {
        "model_provider": "ollama"
    },
    {
        "model_provider": "deepseek"
    }
]
```

### GET `/providers/{provider_name}`

Retrieve a list of all available models for a specific provider.

A small example excerpt could look like this:

```JSON
{
    "model_provider": "ollama",
    "models": [
        {
            "name": "llama3.2:latest"
        }
    ]
}
```
