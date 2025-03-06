"""Question-answering and search functions against a vector database."""
from langchain.retrievers.multi_query import MultiQueryRetriever
from langchain.chains.base import Chain
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_community.vectorstores.pgembedding import CollectionStore
from langchain_community.vectorstores.pgvector import DistanceStrategy, PGVector
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain_core.retrievers import BaseRetriever
from langchain_core.vectorstores import VectorStore
from langchain_core.language_models import BaseChatModel
from langchain_core.documents import Document
from pydantic import BaseModel
from brevia.connection import connection_string
from brevia.collections import single_collection_by_name
from brevia.models import load_chatmodel, load_embeddings
from brevia.prompts import load_qa_prompt, load_condense_prompt
from brevia.settings import get_settings
from brevia.utilities.types import load_type
from brevia.base_retriever import BreviaBaseRetriever


DISTANCE_MAP = {
    'euclidean': DistanceStrategy.EUCLIDEAN,
    'cosine': DistanceStrategy.COSINE,
    'max': DistanceStrategy.MAX_INNER_PRODUCT,
}


class SearchQuery(BaseModel):
    """
    Parameters for a vector-based search query.

    Attributes:
        query (str): The search query text.
        collection (str): The collection name or identifier.
        docs_num (int | None): Max number of documents to retrieve.
        distance_strategy_name (str): Distance strategy, defaults to 'cosine'.
        filter (dict[str, str | dict | list] | None): Optional filter criteria.
    """
    query: str
    collection: str
    docs_num: int | None = None
    distance_strategy_name: str = 'cosine'
    filter: dict[str, str | dict | list] | None = None


class ChatParams(BaseModel):
    """
    Parameters for initiating a Q&A conversation chain.

    Attributes:
        docs_num (int | None): Optional number of documents to retrieve.
        streaming (bool): Flag to determine if the response should be streamed.
        distance_strategy_name (str | None): Optional strategy for distance calculation.
        filter (dict[str, str | dict] | None): Optional filter parameters for retrieval.
        source_docs (bool): Flag to include retrieved source documents in the response.
        multiquery (bool): Flag for executing multiple queries for retrieval.
        search_type (str): Type of search algorithm (default is "similarity").
        score_threshold (float): Threshold for filtering documents by relevance scores.
    """
    docs_num: int | None = None
    streaming: bool = False
    distance_strategy_name: str | None = None
    filter: dict[str, str | dict] | None = None
    source_docs: bool = False
    multiquery: bool = False
    search_type: str = "similarity"
    score_threshold: float = 0.0

    def get_search_kwargs(self) -> dict:
        """ Construct and return keyword arguments needed for search methods. """
        return {
            'k': self.docs_num,
            'filter': self.filter,
            'score_threshold': self.score_threshold,
        }


def search_vector_qa(
    search: SearchQuery,
) -> list[tuple[Document, float]]:
    """
    Execute a vector search for Q&A tasks and return matching documents with scores.

    This function uses the provided search parameters to perform a similarity search
    on the designated collection's vector index. It retrieves a list of document-score
    tuples that best match the input query.
    """
    collection_store = single_collection_by_name(search.collection)
    if not collection_store:
        raise ValueError(f'Collection not found: {search.collection}')
    if search.docs_num is None:
        default_num = get_settings().search_docs_num
        search.docs_num = int(collection_store.cmetadata.get('docs_num', default_num))
    strategy = DISTANCE_MAP.get(search.distance_strategy_name, DistanceStrategy.COSINE)
    embeddings_conf = collection_store.cmetadata.get('embedding', None)
    docsearch = PGVector(
        connection_string=connection_string(),
        embedding_function=load_embeddings(embeddings_conf),
        collection_name=search.collection,
        distance_strategy=strategy,
        use_jsonb=True,
    )

    return docsearch.similarity_search_with_score(
        query=search.query,
        k=search.docs_num,
        filter=search.filter,
    )


def create_custom_retriever(
        store: VectorStore,
        search_kwargs: dict,
        retriever_conf: dict,
) -> BaseRetriever:
    """Create sda custom retriever from a configuration."""
    retriever_name = retriever_conf.pop('retriever', '')
    retriever_class = load_type(retriever_name, BaseRetriever)

    return retriever_class(
        vectorstore=store,
        search_kwargs=search_kwargs,
        **retriever_conf,
    )


def create_default_retriever(
        store: VectorStore,
        search_kwargs: dict,
        llm: BaseChatModel,
        search_type: str | None = None,
        multiquery: bool = False,

) -> BaseRetriever:
    """
        Create a default retriever.
        Can be a vector store retriever or a multiquery retriever.
    """
    retriever = BreviaBaseRetriever(
        vectorstore=store,
        search_type=search_type,
        search_kwargs=search_kwargs
    )

    if multiquery:
        return MultiQueryRetriever.from_llm(retriever=retriever, llm=llm)

    return retriever


def create_conversation_retriever(
    collection: CollectionStore,
    chat_params: ChatParams,
    llm: BaseChatModel,
) -> BaseRetriever:
    """ Create a retriever for a collection with chat parameters """
    strategy = DISTANCE_MAP.get(
        chat_params.distance_strategy_name,
        DistanceStrategy.COSINE
    )

    embeddings_conf = collection.cmetadata.get('embedding', None)
    document_search = PGVector(
        connection_string=connection_string(),
        embedding_function=load_embeddings(embeddings_conf),
        collection_name=collection.name,
        distance_strategy=strategy,
        use_jsonb=True,
    )
    search_kwargs = chat_params.get_search_kwargs()
    retriever_conf = collection.cmetadata.get(
        'qa_retriever',
        get_settings().qa_retriever.copy()
    )
    if not retriever_conf:
        return create_default_retriever(
            store=document_search,
            search_kwargs=search_kwargs,
            llm=llm,
            search_type=chat_params.search_type,
            multiquery=chat_params.multiquery,
        )

    # custom retriever
    return create_custom_retriever(
        document_search, search_kwargs, retriever_conf)


def conversation_chain(
    collection: CollectionStore,
    chat_params: ChatParams,
    answer_callbacks: list[BaseCallbackHandler] | None = None,
) -> Chain:
    """
    Create and return a conversation chain for Q&A with embedded dataset knowledge.

    Args:
        collection (CollectionStore): The collection store item containing the dataset.
        chat_params (ChatParams): Parameters for configuring the conversation chain,
            including:
            - docs_num (int | None): Number of documents to retrieve for context
              (default is from settings or collection metadata).
            - streaming (bool): Flag to enable or disable streaming responses
              (default is False).
            - distance_strategy_name (str | None): Name of the distance strategy to use
              (default is 'cosine').
            - filter (dict[str, str | dict] | None): Optional dictionary of metadata to
              use as a filter (default is None).
            - source_docs (bool): Flag to include source documents in the response
              (default is False).
            - multiquery (bool): Flag to enable multiple queries for retrieval
              (default is False).
            - search_type (str): Type of search algorithm to use (def is 'similarity').
            - score_threshold (float): Threshold for filtering documents based on
              relevance scores (default is 0.0).
        answer_callbacks (list[BaseCallbackHandler] | None): List of callback handlers
            for the final LLM answer to enable streaming (default is None).

    Returns:
        Chain: A configured conversation chain for Q&A tasks.
    """
    settings = get_settings()
    if chat_params.docs_num is None:
        chat_params.docs_num = int(
            collection.cmetadata.get('docs_num', settings.search_docs_num)
        )

    prompts = collection.cmetadata.get('prompts', {})
    prompts = prompts if prompts else {}

    # Main LLM configuration
    qa_llm_conf = collection.cmetadata.get(
        'qa_completion_llm',
        settings.qa_completion_llm.copy()
    )
    qa_llm_conf['callbacks'] = [] if answer_callbacks is None else answer_callbacks
    qa_llm_conf['streaming'] = chat_params.streaming
    chatllm = load_chatmodel(qa_llm_conf)

    # Create Retriever
    retriever = create_conversation_retriever(
        collection=collection,
        chat_params=chat_params,
        llm=chatllm
    )

    # Chain to rewrite question with history
    fup_llm_conf = collection.cmetadata.get(
        'qa_followup_llm',
        settings.qa_followup_llm.copy()
    )
    fup_llm = load_chatmodel(fup_llm_conf)
    fup_chain = (
        load_condense_prompt(prompts.get('condense'))
        | fup_llm
        | StrOutputParser()
    )

    # Chain with "stuff document" type
    document_chain = create_stuff_documents_chain(
        llm=chatllm,
        prompt=load_qa_prompt(prompts)
    )

    retrieval_docs = (lambda x: x["question"]) | retriever
    retrivial_chain = (
        RunnablePassthrough.assign(
            context=retrieval_docs.with_config(run_name="retrieve_documents"),
        ).assign(answer=document_chain)
    ).with_config(run_name="retrieval_chain")

    # Final retrieval chain with proper input handling
    return (
        RunnablePassthrough.assign(
            question=fup_chain
        )
        | retrivial_chain
    )
