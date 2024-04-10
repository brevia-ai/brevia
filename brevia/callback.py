""" Callback class to handle conversation chain events """
from typing import Dict, Any, List, Sequence, Union
from uuid import UUID
import asyncio
import logging
import json
from langchain_community.callbacks import get_openai_callback
from langchain.callbacks.base import BaseCallbackHandler, AsyncCallbackHandler
from langchain.docstore.document import Document
from langchain.schema import BaseMessage
from langchain.schema.output import LLMResult
from langchain.callbacks.openai_info import OpenAICallbackHandler
from brevia.chat_history import add_history


# Only OpenAI token usage callback handler is supported for now
# other LLMs will always return 0 as tokens usage (for now)
token_usage_callback = get_openai_callback
TokensCallbackHandler = OpenAICallbackHandler


def token_usage(callb: TokensCallbackHandler) -> dict[str, int | float]:
    """Tokens usage and costs details (only OpenAI for now)"""
    return {
        'completion_tokens': callb.completion_tokens,
        'prompt_tokens': callb.prompt_tokens,
        'total_tokens': callb.total_tokens,
        'successful_requests': callb.successful_requests,
        'total_cost': callb.total_cost,
    }


class ConversationCallbackHandler(AsyncCallbackHandler):
    """Call back handler to return conversation chain results"""
    result: Dict[str, Any] = {}
    chain_ended = asyncio.Event()

    async def on_chat_model_start(
        self,
        serialized: Dict[str, Any],
        messages: List[List[BaseMessage]],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> Any:
        """Run when a chat model starts running."""

    async def on_chain_start(
        self,
        serialized: Dict[str, Any],
        inputs: Dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """Run when chain starts running."""
        self.chain_ended.clear()

    async def on_chain_end(
        self,
        outputs: Dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """Run when chain ends running."""
        self.result = outputs
        self.chain_ended.set()

    async def wait_conversation_done(self):
        """Wait for conversation end"""
        await self.chain_ended.wait()  # await until event would be .set()

    def chain_result(
        self,
        callb: TokensCallbackHandler,
        question: str,
        collection: str,
        x_chat_session: str | None = None,
    ) -> str:
        """Save chat history and add history id and source_documents to chain result"""
        chat_hist = add_history(
            session_id=x_chat_session,
            collection=collection,
            question=question,
            answer=self.result['answer'].strip(" \n"),
            metadata=token_usage(callb),
        )

        docs = [{'chat_history_id': None if chat_hist is None else str(chat_hist.uuid)}]

        if 'source_documents' in self.result:
            for doc in self.result['source_documents']:
                docs.append({
                    'page_content': doc.page_content,
                    'metadata': doc.metadata
                })

        return json.dumps(docs)


class AsyncLoggingCallbackHandler(AsyncCallbackHandler):
    """Callback handler to handle logging in async calls"""
    log = None

    def __init__(self):
        self.log = logging.getLogger(__name__)
        super().__init__()

    async def on_chat_model_start(
        self,
        serialized: Dict[str, Any],
        messages: List[List[BaseMessage]],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> Any:
        """Run when a chat model starts running."""
        item = f'{run_id} / {parent_run_id}'
        self.log.info("%s - serialized: %s", item, serialized)
        self.log.info("%s - messages: %s", item, messages)

    async def on_chain_start(
        self,
        serialized: Dict[str, Any],
        inputs: Dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """Run when chain starts running."""
        item = f'{run_id} / {parent_run_id}'
        self.log.info("%s - serialized: %s", item, serialized)
        self.log.info("%s - inputs: %s", item, inputs)

    async def on_chain_end(
        self,
        outputs: Dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """Run when chain ends running."""
        item = f'{run_id} / {parent_run_id}'
        self.log.info("%s - outputs: %s", item, outputs)

    async def on_retriever_start(
        self,
        serialized: Dict[str, Any],
        query: str,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: List[str] | None = None,
        metadata: Dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Run on retriever start."""
        item = f'{run_id} / {parent_run_id}'
        self.log.info("%s - query: %s", item, query)
        self.log.info("%s - serialized: %s", item, serialized)

    async def on_retriever_end(
        self,
        documents: Sequence[Document],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: List[str] | None = None,
        **kwargs: Any,
    ) -> None:
        """Run on retriever end."""
        item = f'{run_id} / {parent_run_id}'
        self.log.info("%s - documents: %s", item, documents)

    async def on_retriever_error(
        self,
        error: Union[Exception, KeyboardInterrupt],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: List[str] | None = None,
        **kwargs: Any,
    ) -> None:
        """Run on retriever error."""
        item = f'{run_id} / {parent_run_id}'
        self.log.error("%s - %s", item, error)

    # async def on_text(
    #     self,
    #     text: str,
    #     *,
    #     run_id: UUID,
    #     parent_run_id: UUID | None = None,
    #     **kwargs: Any,
    # ) -> Any:
    #     """Run on arbitrary text."""
        # self.log.info('on_text')
        # self.log.info(text)


class LoggingCallbackHandler(BaseCallbackHandler):
    """Callback handler to handle logging in async calls"""
    log = None

    def __init__(self):
        self.log = logging.getLogger(__name__)
        super().__init__()

    def on_chat_model_start(
        self,
        serialized: Dict[str, Any],
        messages: List[List[BaseMessage]],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> Any:
        """Run when a chat model starts running."""
        item = f'{run_id} / {parent_run_id}'
        self.log.info("%s - serialized: %s", item, serialized)
        self.log.info("%s - messages: %s", item, messages)

    def on_chain_start(
        self,
        serialized: Dict[str, Any],
        inputs: Dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """Run when chain starts running."""
        item = f'{run_id} / {parent_run_id}'
        self.log.info("%s - serialized: %s", item, serialized)
        self.log.info("%s - inputs: %s", item, inputs)

    def on_chain_end(
        self,
        outputs: Dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """Run when chain ends running."""
        item = f'{run_id} / {parent_run_id}'
        self.log.info("%s - outputs: %s", item, outputs)

    def on_llm_start(
        self,
        serialized: Dict[str, Any],
        prompts: List[str],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: List[str] | None = None,
        metadata: Dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        """Run when LLM starts running."""
        item = f'{run_id} / {parent_run_id}'
        self.log.info("%s - serialized: %s", item, serialized)
        self.log.info("%s - prompts: %s", item, prompts)

    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> Any:
        """Run when LLM ends running."""
        item = f'{run_id} / {parent_run_id}'
        self.log.info("%s - response: %s", item, response)

    # def on_text(
    #     self,
    #     text: str,
    #     *,
    #     run_id: UUID,
    #     parent_run_id: UUID | None = None,
    #     **kwargs: Any,
    # ) -> Any:
    #     """Run on arbitrary text."""
    #     self.log.info('on_text')
    #     self.log.info(text)
