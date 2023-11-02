""" Callback class to handle conversation chain events """
from typing import Dict, Any, List, Sequence, Union
from uuid import UUID
import asyncio
import logging
import json
from langchain.callbacks.base import BaseCallbackHandler, AsyncCallbackHandler
from langchain.docstore.document import Document
from langchain.schema import BaseMessage
from langchain.schema.output import LLMResult


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

    def chain_result(self) -> str:
        """Return chain result"""
        if 'source_documents' not in self.result:
            return ''

        docs = []
        for doc in self.result['source_documents']:
            docs.append({'page_content': doc.page_content, 'metadata': doc.metadata})

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
