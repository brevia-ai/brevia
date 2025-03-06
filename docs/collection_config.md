# Collection Configuration

Specific configuration options for a single `collection` can be set in Brevia. Those options are stored as JSON in `langchain_pg_collection.cmetadata` database column and are used mainly for RAG applications.

This way you can also override some [global configurations](config.md) on a specific `collection` to use, for instance, different LLM settings or embeddings/indexing strategies.

All configuration items described here below can be set as keys in `cmetadata` JSON field of a single collection using [`PATCH /collections/{{collection_id}}` endpoint](endpoints_overview.md#collections-endpoints)

## Prompt

- `prompts` (JSON) configuration of the custom prompts used in the [Q&A & chat](chat_search.md) actions, see [Prompt Management](prompt_management.md) for more details.

## Index and search

### Embeddings

- `embeddings` (JSON) configuration for the embedding engins - overrides [`EMBEDDINGS`](config.md#embeddings)

### Text Segmentation

- `chunk_size` (integer) maximum size of individual text chunks in documents index - overrides [``TEXT_CHUNK_SIZE`](config.md#text-segmentation)
- `chunk_overlap` (integer) amount of overlap between consecutive text chunk - overrides [``TEXT_CHUNK_OVERLAP`](config.md#text-segmentation)
- `text_splitter` (JSON) configuration of a custom text splitter - overrides [``TEXT_CHUNK_OVERLAP`](config.md#text-segmentation)

### Search

- `docs_num` (integer) the number of documents to extract in a search or Q&A action - will override [`SEARCH_DOCS_NUM`](config.md#qa-and-chat)

## Q&A and Chat

You can configure models and behaviors of [Q&A and chat actions](chat_search.md) via these variables:

- `qa_completion_llm` (JSON) configuration for the main conversational model - overrides [`QA_COMPLETION_LLM`](config.md#qa-and-chat)
- `qa_followup_llm` (JSON) configuration for the follow-up question model - overrides [`QA_FOLLOWUP_LLM`](config.md#qa-and-chat)
- `qa_retriever` (JSON) configuration for a custom retriever class - overrides [`QA_RETRIEVER`](config.md#qa-and-chat)

## Documents

There are some document related configurations that are collection-specific and are not present in the global configurations.

### Metadata

- `documents_metadata` (JSON) JSON Schema of the documents metadata
- `metadata_defaults` (JSON) default values of the documents metadata, if any, divided by document type

### Load Options

- `file_upload_options` (JSON) custom options when loading files, for instance OCR options for PDFs
- `link_load_options` (JSON) custom options when loading links, for instance selector rules to use
