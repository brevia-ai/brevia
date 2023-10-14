"""Base service and some basic implementations"""
from abc import ABC, abstractmethod
from os import environ, unlink
from langchain.callbacks import get_openai_callback
from brevia import load_file, query


class BaseService(ABC):
    """Base class for services"""
    def run(self, payload: dict) -> dict:
        """Run a service using a payload"""
        if not self.validate(payload):
            raise ValueError(f'Invalid service payload - {payload}')
        return self.execute(payload)

    @abstractmethod
    def execute(self, payload: dict) -> dict:
        """Execute service logic using payload"""

    @abstractmethod
    def validate(self, payload: dict) -> bool:
        """Validate service payload"""


class SummarizeTextService(BaseService):
    """Service to perform summarization from text input"""

    def execute(self, payload: dict):
        """Service logic"""
        token_data = payload.pop('token_data')
        with get_openai_callback() as callb:
            result = query.summarize(**payload)

        return {
            'output': result,
            'token_data': None if not token_data else callb.__dict__
        }

    def validate(self, payload: dict):
        """Payload validation"""
        if not payload.get('text'):
            return False
        return True


class SummarizeFileService(BaseService):
    """Service to perform summarization from file input"""

    def execute(self, payload: dict):
        """Service logic"""
        return self.summarize_from_file(**payload)

    def validate(self, payload: dict):
        """Payload validation"""
        if not payload.get('file_path'):
            return False
        return True

    def summarize_from_file(
        self,
        file_path: str,
        summ_prompt: str = environ.get('SUMM_DEFAULT_PROMPT', 'summarize'),
        num_items: int = int(environ.get('SUMM_NUM_ITEMS', '5')),
        token_data: bool = False,
    ) -> dict:
        """
        Perform summarization of a temporary PDF file.
        File is removed after summarization.
        """
        try:
            text = load_file.read_pdf_file(file_path=file_path)
        finally:
            unlink(file_path)  # Delete the temp file

        if not text:
            raise ValueError('Empty text field')

        with get_openai_callback() as callb:
            result = query.summarize(
                text,
                num_items=num_items,
                summ_prompt=summ_prompt,
            )

        return {
            'output': result,
            'token_data': None if not token_data else callb.__dict__
        }


class FakeService(BaseService):
    """Fake class for services testing"""
    def execute(self, payload: dict) -> dict:
        return {'success': True}

    def validate(self, payload: dict) -> bool:
        return True
