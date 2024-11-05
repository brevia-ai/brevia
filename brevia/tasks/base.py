"""Base class for analysis tasks"""
from abc import ABC, abstractmethod
from typing import Any
from brevia.settings import get_settings


class BaseAnalysisTask(ABC):
    """Base class for analysis tasks"""
    prompts: dict[str, Any] = {}

    @abstractmethod
    def perform_task(self) -> dict:
        """Perform task logic using payload"""

    @abstractmethod
    def load_analysis_prompts(self, prompts: dict | None = None):
        """Load analysis prompts usign optional input prompts"""

    @classmethod
    def prompt_path(cls, file_name: str) -> str:
        """Prompt path"""
        return f'{get_settings().prompts_base_path}/{file_name}'
