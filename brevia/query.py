"""Returning text summarize or question-answering chain against a vector database."""
from os import environ, path
import logging
from langchain.docstore.document import Document
from langchain.vectorstores.pgvector import PGVector, DistanceStrategy
from langchain.vectorstores._pgvector_data_models import CollectionStore
from langchain.callbacks.base import BaseCallbackHandler
from langchain.chains.base import Chain
from langchain.chains.summarize import load_summarize_chain
from langchain.text_splitter import TokenTextSplitter
from langchain.chains import ConversationalRetrievalChain
from langchain.chains.question_answering import load_qa_chain
from langchain.chains.llm import LLMChain
from langchain.prompts import load_prompt
from langchain.prompts import (
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
)
from langchain.prompts.loading import load_prompt_from_config
from langchain.chat_models import ChatOpenAI
from brevia import connection, index
from brevia.callback import AsyncLoggingCallbackHandler, LoggingCallbackHandler


def load_brevia_prompt(prompts: dict | None) -> ChatPromptTemplate:
    """ load prompts for Q/A functions """

    prompts_path = f'{path.dirname(__file__)}/prompts'
    system = load_prompt(f'{prompts_path}/qa/default.system.yaml')
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


def search_vector_qa(
    query: str,
    collection: str,
    docs_num: int = int(environ.get('SEARCH_DOCS_NUM', 4)),
    distance_strategy_name: str = 'cosine',
) -> list[tuple[Document, float]]:
    """ Perform a similarity search on vector index """

    docsearch = PGVector(
        connection_string=connection.connection_string(),
        embedding_function=index.get_embeddings(),
        collection_name=collection,
        distance_strategy=distance_strategy(distance_strategy_name),
    )

    return docsearch.similarity_search_with_score(query, k=docs_num)


def distance_strategy(strategy: str):
    """Distance strategy from type name"""
    distance_map = {
        'euclidean': DistanceStrategy.EUCLIDEAN,
        'cosine': DistanceStrategy.COSINE,
        'max': DistanceStrategy.MAX_INNER_PRODUCT,
    }
    if strategy not in distance_map:
        return DistanceStrategy.COSINE

    return distance_map[strategy]


def conversation_chain(
    # pylint: disable=too-many-arguments
    collection: CollectionStore,
    docs_num: int | None,
    source_docs: bool = True,
    distance_strategy_name: str = 'cosine',
    streaming: bool = False,
    answer_callbacks: list[BaseCallbackHandler] = [],
    conversation_callbacks: list[BaseCallbackHandler] = [],
) -> Chain:
    """
        Return conversation chain for Q/A with embdedded dataset knowledge

        collection: name of collection to questioning
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

    docsearch = PGVector(
        connection_string=connection.connection_string(),
        embedding_function=index.get_embeddings(),
        collection_name=collection.name,
        distance_strategy=distance_strategy(distance_strategy_name),
    )

    prompts = collection.cmetadata.get('prompts')
    model_name = collection.cmetadata.get('model_name', environ.get('QA_MODEL'))
    temperature = collection.cmetadata.get('temperature', environ.get('QA_TEMPERATURE'))
    verbose = environ.get('VERBOSE_MODE', False)

    # Model for rewriting follow-up question
    fup_llm = ChatOpenAI(
        model_name=environ.get('QA_FOLLOWUP_MODEL', 'gpt-3.5-turbo'),
        temperature=float(temperature),
        max_tokens=int(environ.get('QA_FOLLOWUP_MAX_TOKENS', 200)),
        verbose=verbose,
    )

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
    chatllm = ChatOpenAI(
        model_name=model_name,
        temperature=float(temperature),
        max_tokens=int(environ.get('QA_MAX_TOKENS', 800)),
        callbacks=answer_callbacks,
        streaming=streaming,
        verbose=verbose,
    )

    # this chain use "stuff" to elaborate context
    doc_chain = load_qa_chain(
        llm=chatllm,
        prompt=load_brevia_prompt(prompts),
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


def summarize(
    text: str,
    num_items: int = int(environ.get('SUMM_NUM_ITEMS', 5)),
    summ_prompt: str = environ.get('SUMM_DEFAULT_PROMPT')
) -> str:
    """ Perform summarizing for a given text """

    if bool(environ.get('FAKE_SUMMARY')):
        print('Using FAKE summary - text truncate!!')
        logging.getLogger(__name__).warning('Using FAKE summary - text truncate!!')
        import time  # pylint: disable=import-outside-toplevel
        time.sleep(30)
        return text[:min(100, len(text)-1)]

    text_splitter = TokenTextSplitter(
        chunk_size=int(environ.get("SUMM_TOKEN_SPLITTER", 4000)),
        chunk_overlap=int(environ.get("SUMM_TOKEN_OVERLAP", 500))
    )
    texts = text_splitter.split_text(text)
    docs = [Document(page_content=t) for t in texts]
    lang = environ.get("PROMPT_LANG", 'it')

    # TODO: refactor with dynamics summary types
    if summ_prompt not in ['summarize', 'summarize_point', 'classificate']:
        summ_prompt = 'summarize'
    prompts_path = f'{path.dirname(__file__)}/prompts'
    prompt = load_prompt(f'{prompts_path}/summarize/yaml/{lang}.{summ_prompt}.yaml')
    logging_handler = LoggingCallbackHandler()
    chain = load_summarize_chain(
        ChatOpenAI(
            model_name=environ.get("SUMM_COMPLETIONS_MODEL"),
            temperature=float(environ.get("SUMM_TEMPERATURE", 0)),
            max_tokens=int(environ.get("SUMM_MAX_TOKENS", 2000)),
            callbacks=[logging_handler],
        ),
        chain_type='map_reduce',
        map_prompt=prompt,
        verbose=environ.get("VERBOSE_MODE", False),
        combine_prompt=prompt,
        callbacks=[logging_handler],
    )
    return chain.run(**{'input_documents': docs, 'num_items': num_items})
