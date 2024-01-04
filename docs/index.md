# Brevia in a nutshell

Brevia is an extensible API and framework to build your Retrieval Augmented Generation (RAG) and Information Extraction (IE) applications with LLMs.

Ouf of the box Brevia provides:

* a complete API for RAG applications
* an API with Information extractions capabilities like summarization, with the possibility to create your own analysis logic with asycnhronous background operations support

Brevia uses:

* the popular [LangChain](https://github.com/langchain-ai/langchain) framework that you can use to create your custom AI tools and logic
* the [FastAPI](https://github.com/tiangolo/fastapi) framework to easily extend your application with new endpoints
* [PostgreSQL](https://www.postgresql.org) with [`pg_vector`](https://github.com/pgvector/pgvector) extension as vector database
