from typing import List
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.vectorstores import VectorStore, VectorStoreRetriever


class BreviaBaseRetriever(VectorStoreRetriever):
    """ Base custom Retriever for BREVIA"""

    vectorstore: VectorStore
    """VectorStore used for retrieval."""

    search_kwargs: dict
    """Configuration containing settings for the search from the application"""

    async def _aget_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> List[Document]:
        """
        Asynchronous implementation for retrieving relevant documents with score
        Merges results from multiple custom searches using different filters.

        Parameters:
            query (str): The search query.
            run_manager (CallbackManagerForRetrieverRun): Manager for retriever runs.

        Returns:
            List[Document]: A list of relevant documents based on the search.
        """
        if self.search_type == "similarity":
            docs = await self.vectorstore.asimilarity_search(
                query, **self.search_kwargs
            )
        elif self.search_type == "similarity_score_threshold":
            docs_and_similarities = (
                await self.vectorstore.asimilarity_search_with_relevance_scores(
                    query, **self.search_kwargs
                )
            )
            for doc, score in docs_and_similarities:
                doc.metadata["score"] = score
            docs = [doc for doc, _ in docs_and_similarities]
        elif self.search_type == "mmr":
            docs = await self.vectorstore.amax_marginal_relevance_search(
                query, **self.search_kwargs
            )
        else:
            msg = f"search_type of {self.search_type} not allowed."
            raise ValueError(msg)
        return docs
