"""Question-answering and search functions against a vector database."""
from os import path
from langchain.retrievers.multi_query import MultiQueryRetriever
from langchain.chains.base import Chain
from langchain.chains.conversational_retrieval.base import ConversationalRetrievalChain
from langchain.chains.question_answering import load_qa_chain
from langchain_core.language_models import BaseLanguageModel
from langchain_core.retrievers import BaseRetriever
from langchain_core.vectorstores import VectorStore
from langchain.chains.llm import LLMChain
from langchain_community.vectorstores.pgembedding import CollectionStore
from langchain_community.vectorstores.pgvector import DistanceStrategy, PGVector
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.documents import Document
from langchain_core.prompts import (
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
    PromptTemplate,
    SystemMessagePromptTemplate,
    load_prompt,
)
from langchain_core.prompts.loading import load_prompt_from_config
from pydantic import BaseModel
from brevia.connection import connection_string
from brevia.collections import single_collection_by_name
from brevia.callback import AsyncLoggingCallbackHandler
from brevia.models import load_chatmodel, load_embeddings
from brevia.settings import get_settings
from brevia.utilities.types import load_type

# system = load_prompt(f'{prompts_path}/qa/default.system.yaml')
# jinja2 template from file was disabled by langchain so, for now
# we load from here
SYSTEM_TEMPLATE = """
                As an AI assistant your task is to provide valuable
                information and support to our users. Answer the question
                as truthfully as possible using the provided context
                between ##Context start## and ##Context end##.
                If the answer is not contained within the provided context,
                say that you are sorry but that you cannot answer
                to that question. Don't try to make up an answer.
                ##Context start## {{context}} ##Context end##
                Answer in {% if lang|length %}{{ lang }}{% else %}
                the same language of the question{% endif %}
                """


def load_qa_prompt(prompts: dict | None) -> ChatPromptTemplate:
    """
        load prompts for RAG-Q/A functions, following openIA system/human/ai pattern:
        SYSTEM_TEMPLATE: is a jinja2 template with language checking from api call.
                         For security reason, the default is loaded from here and
                         overwritten from api call.
        HUMAN_TEMPLATE:  is a normal template, loaded from /prompts/qa and overwritten
                         by api call

    """

    prompts_path = f'{path.dirname(__file__)}/prompts'
    system = PromptTemplate.from_template(SYSTEM_TEMPLATE, template_format="jinja2")
    human = load_prompt(f'{prompts_path}/qa/default.human.yaml')

    if prompts:
        if prompts.get('system'):
            system = load_prompt_from_config(prompts.get('system'))
        if prompts.get('human'):
            human = load_prompt_from_config(prompts.get('human'))

    system_message_prompt = SystemMessagePromptTemplate(prompt=system)
    human_message_prompt = HumanMessagePromptTemplate(prompt=human)

    return ChatPromptTemplate.from_messages(
        [system_message_prompt, human_message_prompt]
    )


def load_condense_prompt(prompts: dict | None) -> ChatPromptTemplate:
    """
        Check if specific few-shot prompt file exists for the collection, if not,
        check for condense prompt file, otherwise, load default condense prompt file.
        few-shot can improve condensing the chat history especially when the chat
        history is about eterogenous topics.
    """
    if prompts:
        if prompts.get('few'):
            return load_prompt_from_config(prompts.get('few'))
        if prompts.get('condense'):
            return load_prompt_from_config(prompts.get('condense'))

    prompts_path = f'{path.dirname(__file__)}/prompts'

    return load_prompt(f'{prompts_path}/qa/default.condense.yaml')


DISTANCE_MAP = {
    'euclidean': DistanceStrategy.EUCLIDEAN,
    'cosine': DistanceStrategy.COSINE,
    'max': DistanceStrategy.MAX_INNER_PRODUCT,
}


class SearchQuery(BaseModel):
    """ Search query items """
    query: str
    collection: str
    docs_num: int | None = None
    distance_strategy_name: str = 'cosine'
    filter: dict[str, str | dict | list] | None = None


def search_vector_qa(
    search: SearchQuery,
) -> list[tuple[Document, float]]:
    """ Perform a similarity search on vector index """
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


class ChatParams(BaseModel):
    """ Q&A basic conversation chain params"""
    docs_num: int | None = None
    streaming: bool = False
    distance_strategy_name: str | None = None
    filter: dict[str, str | dict] | None = None
    source_docs: bool = False
    multiquery: bool = False


def create_custom_retriever(
        store: VectorStore,
        search_kwargs: dict,
        retriever_conf: dict,
) -> BaseRetriever:
    """
        Create a custom retriever from a configuration.
    """
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
        llm: BaseLanguageModel,
        multiquery: bool = False,

) -> BaseRetriever:
    """
        Create a default retriever.
        Can be a vector store retriever or a multiquery retriever.
    """
    retriever = store.as_retriever(search_kwargs=search_kwargs)
    if multiquery:
        return MultiQueryRetriever.from_llm(retriever=retriever, llm=llm)

    return retriever


def conversation_chain(
    collection: CollectionStore,
    chat_params: ChatParams,
    answer_callbacks: list[BaseCallbackHandler] | None = None,
    conversation_callbacks: list[BaseCallbackHandler] | None = None,
) -> Chain:
    """
        Return conversation chain for Q/A with embdedded dataset knowledge

        collection: collection store item
        chat_params: basic conversation chain parameters, including:
            docs_num: number of docs to retrieve to create context
                (default 'SEARCH_DOCS_NUM' env var or '4')
            streaming: activate streaming (default False),
            distance_strategy_name: distance strategy to use (default 'cosine')
            filter: optional dictionary of metadata to use as filter (defailt None)
            source_docs: flag to retrieve source docs in response (default True)
        answer_callbacks: callbacks to use in the final LLM answer to enable streaming
            (default empty list)
        conversation_callbacks: callback to handle conversation results
            (default empty list)
        multiquery: flag for activate langchain's multiquery retriver

        can implement "vectordbkwargs" into quest_dict:
            {
                "search_distance": 0.9
            }
    """
    settings = get_settings()
    if chat_params.docs_num is None:
        default_num = settings.search_docs_num
        chat_params.docs_num = int(collection.cmetadata.get('docs_num', default_num))
    if answer_callbacks is None:
        answer_callbacks = []
    if conversation_callbacks is None:
        conversation_callbacks = []

    strategy = DISTANCE_MAP.get(
        chat_params.distance_strategy_name,
        DistanceStrategy.COSINE
    )
    docsearch = PGVector(
        connection_string=connection_string(),
        embedding_function=load_embeddings(collection.cmetadata.get('embedding', None)),
        collection_name=collection.name,
        distance_strategy=strategy,
        use_jsonb=True,
    )

    prompts = collection.cmetadata.get('prompts')
    qa_llm_conf = collection.cmetadata.get(
        'qa_completion_llm',
        settings.qa_completion_llm.copy()
    )
    fup_llm_conf = collection.cmetadata.get(
        'qa_followup_llm',
        settings.qa_followup_llm.copy()
    )

    verbose = settings.verbose_mode

    # LLM to rewrite follow-up question
    fup_llm = load_chatmodel(fup_llm_conf)

    logging_handler = AsyncLoggingCallbackHandler()
    # Create chain for follow-up question using chat history (if present)
    question_generator = LLMChain(
        llm=fup_llm,
        prompt=load_condense_prompt(prompts),
        verbose=verbose,
        callbacks=[logging_handler],
    )

    # Model to use in final prompt
    answer_callbacks.append(logging_handler)
    qa_llm_conf['callbacks'] = answer_callbacks
    qa_llm_conf['streaming'] = chat_params.streaming
    chatllm = load_chatmodel(qa_llm_conf)

    # this chain use "stuff" to elaborate context
    doc_chain = load_qa_chain(
        llm=chatllm,
        prompt=load_qa_prompt(prompts),
        chain_type="stuff",
        verbose=verbose,
        callbacks=[logging_handler],
    )

    # main chain, do all the jobs
    search_kwargs = {'k': chat_params.docs_num, 'filter': chat_params.filter}
    retriever_conf = collection.cmetadata.get(
        'qa_retriever',
        settings.qa_retriever.copy()
    )
    if not retriever_conf:
        retriever = create_default_retriever(
            store=docsearch,
            search_kwargs=search_kwargs,
            llm=chatllm,
            multiquery=chat_params.multiquery,
        )
    else:   # custom retriever
        retriever = create_custom_retriever(docsearch, search_kwargs, retriever_conf)

    conversation_callbacks.append(logging_handler)

    return ConversationalRetrievalChain(
        retriever=retriever,
        combine_docs_chain=doc_chain,
        return_source_documents=chat_params.source_docs,
        question_generator=question_generator,
        callbacks=conversation_callbacks,
        verbose=verbose,
    )
