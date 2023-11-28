"""Question-answering and search functions against a vector database."""
from os import environ, path
from langchain.docstore.document import Document
from langchain.vectorstores.pgvector import PGVector, DistanceStrategy
from langchain.vectorstores._pgvector_data_models import CollectionStore
from langchain.callbacks.base import BaseCallbackHandler
from langchain.chains.base import Chain
from langchain.chains import ConversationalRetrievalChain
from langchain.chains.question_answering import load_qa_chain
from langchain.chains.llm import LLMChain
from langchain.prompts import PromptTemplate
from langchain.prompts import load_prompt
from langchain.prompts import (
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
)
from langchain.prompts.loading import load_prompt_from_config
from brevia.connection import connection_string
from brevia.collections import single_collection_by_name
from brevia.callback import AsyncLoggingCallbackHandler
from brevia.models import load_chatmodel, load_embeddings

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
    """ load prompts for Q/A functions """

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


def search_vector_qa(
    query: str,
    collection: str,
    docs_num: int | None = None,
    distance_strategy_name: str = 'cosine',
) -> list[tuple[Document, float]]:
    """ Perform a similarity search on vector index """
    collection_store = single_collection_by_name(collection)
    if not collection_store:
        raise ValueError(f'Collection not found: {collection}')
    if docs_num is None:
        default_num = environ.get('SEARCH_DOCS_NUM', 4)
        docs_num = int(collection_store.cmetadata.get('docs_num', default_num))
    strategy = DISTANCE_MAP.get(distance_strategy_name, DistanceStrategy.COSINE)
    docsearch = PGVector(
        connection_string=connection_string(),
        embedding_function=load_embeddings(),
        collection_name=collection,
        distance_strategy=strategy,
    )

    return docsearch.similarity_search_with_score(query, k=docs_num)


def conversation_chain(
    # pylint: disable=too-many-arguments
    collection: CollectionStore,
    docs_num: int | None = None,
    source_docs: bool = True,
    distance_strategy_name: str = 'cosine',
    streaming: bool = False,
    answer_callbacks: list[BaseCallbackHandler] | None = None,
    conversation_callbacks: list[BaseCallbackHandler] | None = None,
) -> Chain:
    """
        Return conversation chain for Q/A with embdedded dataset knowledge

        collection: collection store item
        docs_num: number of docs to retrieve to create context
            (default 'SEARCH_DOCS_NUM' env var or '4')
        source_docs: flag to retrieve source docs in response (default True)
        distance_strategy_name: distance strategy to use (default 'cosine')
        streaming: activate streaming (default False),
        answer_callbacks: callbacks to use in the final LLM answer to enable streaming
            (default empty list)
        conversation_callbacks: callback to handle conversation results
            (default empty list)

        can implement "vectordbkwargs" into quest_dict:
            {
                "search_distance": 0.9
            }
    """
    if docs_num is None:
        default_num = environ.get('SEARCH_DOCS_NUM', 4)
        docs_num = int(collection.cmetadata.get('docs_num', default_num))
    if answer_callbacks is None:
        answer_callbacks = []
    if conversation_callbacks is None:
        conversation_callbacks = []

    strategy = DISTANCE_MAP.get(distance_strategy_name, DistanceStrategy.COSINE)
    docsearch = PGVector(
        connection_string=connection_string(),
        embedding_function=load_embeddings(),
        collection_name=collection.name,
        distance_strategy=strategy,
    )

    prompts = collection.cmetadata.get('prompts')
    model_name = collection.cmetadata.get('model_name', environ.get('QA_MODEL'))
    temperature = collection.cmetadata.get('temperature', environ.get('QA_TEMPERATURE'))
    verbose = environ.get('VERBOSE_MODE', False)

    # LLM to rewrite follow-up question
    fup_llm = load_chatmodel({
        '_type': 'openai-chat',
        'model_name': environ.get('QA_FOLLOWUP_MODEL', 'gpt-3.5-turbo'),
        'temperature': float(temperature),
        'max_tokens': int(environ.get('QA_FOLLOWUP_MAX_TOKENS', 200)),
        'verbose': verbose,
    })

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
    chatllm = load_chatmodel({
        '_type': 'openai-chat',
        'model_name': model_name,
        'temperature': float(temperature),
        'max_tokens': int(environ.get('QA_MAX_TOKENS', 800)),
        'callbacks': answer_callbacks,
        'streaming': streaming,
        'verbose': verbose,
    })

    # this chain use "stuff" to elaborate context
    doc_chain = load_qa_chain(
        llm=chatllm,
        prompt=load_qa_prompt(prompts),
        chain_type="stuff",
        verbose=verbose,
        callbacks=[logging_handler],
    )

    # main chain, do all the jobs
    search_kwargs = {'k': docs_num}

    conversation_callbacks.append(logging_handler)
    return ConversationalRetrievalChain(
        retriever=docsearch.as_retriever(search_kwargs=search_kwargs),
        combine_docs_chain=doc_chain,
        return_source_documents=source_docs,
        question_generator=question_generator,
        callbacks=conversation_callbacks,
        verbose=verbose,
    )
