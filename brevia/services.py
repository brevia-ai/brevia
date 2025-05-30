"""Base service and some basic implementations"""
from abc import ABC, abstractmethod
from os import unlink
from brevia.callback import token_usage_callback
from brevia.tasks.text_analysis import RefineTextAnalysisTask, SummarizeTextAnalysisTask

from brevia.load_file import read
from brevia.utilities.output import LinkedFileOutput


class BaseService(ABC):
    """Base class for services"""
    job_id = None

    def run(self, payload: dict) -> dict:
        """Run a service using a payload"""
        if not self.validate(payload):
            raise ValueError(f'Invalid service payload - {payload}')
        self.job_id = payload.get('job_id')
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
        analysis = SummarizeTextAnalysisTask(
            text=payload['text'],
            chain_type=payload['chain_type'],
            initial_prompt=payload.get('initial_prompt'),
            iteration_prompt=payload.get('iteration_prompt'),
            text_options=payload.get('text_options')
        )
        with token_usage_callback() as callb:
            result = analysis.perform_task()
        token_data = callb.__dict__
        token_data.pop('_lock', None)

        return {
            'output': result['output_text'],
            'token_data': token_data
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
            text = read(file_path=file_path)
        finally:
            unlink(file_path)  # Delete the temp file

        if not text:
            raise ValueError('Empty text')

        analysis = SummarizeTextAnalysisTask(
            text=text,
            chain_type=chain_type,
            initial_prompt=initial_prompt,
            iteration_prompt=iteration_prompt
        )

        with token_usage_callback() as callb:
            result = analysis.perform_task()

        return {
            'output': result['output_text'],
            'token_data': None if not token_data else callb.__dict__
        }


class RefineTextAnalysisService(BaseService):
    """Service to perform text analysis from text input"""

    def execute(self, payload: dict):
        """Service logic"""
        analysis = RefineTextAnalysisTask(
            file_path=payload['file_path'],
            prompts=payload['prompts'],
            llm_conf=payload.get('llm_conf'),
            text_options=payload.get('text_options')
        )
        with token_usage_callback() as callb:
            result = analysis.perform_task()
        token_data = callb.__dict__
        token_data.pop('_lock', None)

        return {
            'output': result['output_text'],
            'token_data': token_data
        }

    def validate(self, payload: dict):
        """Payload validation"""
        if not payload.get('file_path') or not payload.get('prompts'):
            return False
        prompts = payload['prompts']
        if 'initial_prompt' not in prompts or 'refine_prompt' not in prompts:
            return False

        return True


class RefineTextAnalysisToTxtService(RefineTextAnalysisService):
    """Service to perform text analysis from file, creating a txt file as output"""

    def execute(self, payload: dict):
        """Service logic"""
        result = super().execute(payload)
        file_out = LinkedFileOutput(job_id=self.job_id)
        file_name = 'summary.txt'
        if payload.get('file_name'):
            file_name = payload['file_name'].rsplit('.', 1)[0] + '.txt'
        url = file_out.write(result['output'], file_name)
        result['artifacts'] = [{
            'name': file_name,
            'url': url,
        }]
        return result


class FakeService(BaseService):
    """Fake class for services testing"""

    def execute(self, payload: dict) -> dict:
        return {'output': 'ok'}

    def validate(self, payload: dict) -> bool:
        return True
