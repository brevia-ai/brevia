"""Base service and some basic implementations"""
from abc import ABC, abstractmethod
from os import unlink
from langchain.callbacks import get_openai_callback
from brevia import load_file, analysis


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
            result = analysis.summarize(**payload)

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
        keys = ['file_path', 'chain_type', 'initial_prompt',
                'iteration_prompt', 'token_data']
        args = dict(filter(lambda item: item[0] in keys, payload.items()))

        return self.summarize_from_file(**args)

    def validate(self, payload: dict):
        """Payload validation"""
        if not payload.get('file_path'):
            return False
        return True

    def summarize_from_file(
        self,
        file_path: str,
        chain_type: str | None = None,
        initial_prompt: dict | None = None,
        iteration_prompt: dict | None = None,
        token_data: bool = False,
    ) -> dict:
        """
        Perform summarization of a temporary PDF or TXT file.
        File is removed after summarization.
        """
        try:
            text = load_file.read(file_path=file_path)
        finally:
            unlink(file_path)  # Delete the temp file

        if not text:
            raise ValueError('Empty text')

        with get_openai_callback() as callb:
            result = analysis.summarize(
                text,
                chain_type=chain_type,
                initial_prompt=initial_prompt,
                iteration_prompt=iteration_prompt
            )

        return {
            'output': result,
            'token_data': None if not token_data else callb.__dict__
        }


class FakeService(BaseService):
    """Fake class for services testing"""
    def execute(self, payload: dict) -> dict:
        return {'output': 'ok'}

    def validate(self, payload: dict) -> bool:
        return True
