""" Tests for the BreviaBaseRetriever class. """
import pytest
from unittest.mock import AsyncMock, MagicMock
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.vectorstores import VectorStore
from brevia.base_retriever import BreviaBaseRetriever


@pytest.fixture
def mock_vectorstore():
    """
    Fixture to create a mock VectorStore
    with predefined return values for search methods.

    Returns:
        MagicMock: A mock instance of VectorStore.
    """
    vectorstore = MagicMock(VectorStore)
    vectorstore.asimilarity_search = AsyncMock(
        return_value=[Document(page_content="doc1"), Document(page_content="doc2")])
    vectorstore.asimilarity_search_with_relevance_scores = AsyncMock(
        return_value=[
            (Document(page_content="doc1"), 0.9),
            (Document(page_content="doc2"), 0.8)
        ]
    )
    vectorstore.amax_marginal_relevance_search = AsyncMock(
        return_value=[Document(page_content="doc1"), Document(page_content="doc2")])
    return vectorstore


@pytest.fixture
def search_kwargs():
    """
    Fixture to provide default search keyword arguments.

    Returns:
        dict: A dictionary containing default search keyword arguments.
    """
    return {'k': 2, 'filter': None, 'score_threshold': 0.0}


@pytest.fixture
def retriever(mock_vectorstore, search_kwargs):
    """
    Fixture to create an instance of BreviaBaseRetriever with mock dependencies.

    Args:
        mock_vectorstore (MagicMock): A mock instance of VectorStore.
        search_kwargs (dict): Default search keyword arguments.

    Returns:
        BreviaBaseRetriever: An instance of BreviaBaseRetriever.
    """
    return BreviaBaseRetriever(
        vectorstore=mock_vectorstore,
        search_kwargs=search_kwargs
    )


@pytest.mark.asyncio
async def test_similarity_search(retriever):
    """
    Test the similarity search functionality of BreviaBaseRetriever.

    Args:
        retriever (BreviaBaseRetriever): An instance of BreviaBaseRetriever.
    """
    retriever.search_type = "similarity"
    run_manager = MagicMock(CallbackManagerForRetrieverRun)
    docs = await retriever._aget_relevant_documents(
        query="test query",
        run_manager=run_manager
    )
    assert len(docs) == 2
    assert docs[0].page_content == "doc1"
    assert docs[1].page_content == "doc2"


@pytest.mark.asyncio
async def test_similarity_score_threshold_search(retriever):
    """
    Test the similarity score search functionality of BreviaBaseRetriever.

    Args:
        retriever (BreviaBaseRetriever): An instance of BreviaBaseRetriever.
    """
    retriever.search_type = "similarity_score_threshold"
    run_manager = MagicMock(CallbackManagerForRetrieverRun)
    docs = await retriever._aget_relevant_documents(
        query="test query",
        run_manager=run_manager
    )
    assert len(docs) == 2
    assert docs[0].page_content == "doc1"
    assert docs[0].metadata["score"] == 0.9
    assert docs[1].page_content == "doc2"
    assert docs[1].metadata["score"] == 0.8


@pytest.mark.asyncio
async def test_mmr_search(retriever):
    """
    Test the Maximal Marginal Relevance (MMR)
    search functionality of BreviaBaseRetriever.

    Args:
        retriever (BreviaBaseRetriever): An instance of BreviaBaseRetriever.
    """
    retriever.search_type = "mmr"
    run_manager = MagicMock(CallbackManagerForRetrieverRun)
    docs = await retriever._aget_relevant_documents(
        query="test query",
        run_manager=run_manager
    )
    assert len(docs) == 2
    assert docs[0].page_content == "doc1"
    assert docs[1].page_content == "doc2"


@pytest.mark.asyncio
async def test_invalid_search_type(retriever):
    """
    Test the behavior of BreviaBaseRetriever when an invalid search type is provided.

    Args:
        retriever (BreviaBaseRetriever): An instance of BreviaBaseRetriever.
    """
    retriever.search_type = "invalid_type"
    run_manager = MagicMock(CallbackManagerForRetrieverRun)
    with pytest.raises(ValueError, match="search_type of invalid_type not allowed."):
        await retriever._aget_relevant_documents(
            query="test query",
            run_manager=run_manager
        )
