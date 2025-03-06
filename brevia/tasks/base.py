"""Base class for analysis tasks"""
from abc import ABC, abstractmethod
from typing import Any


class BaseAnalysisTask(ABC):
    """Base class for analysis tasks"""
    prompts: dict[str, Any] = {}

    @abstractmethod
    def perform_task(self) -> dict:
        """Perform task logic using payload"""

    @abstractmethod
    def load_analysis_prompts(self, prompts: dict | None = None):
        """Load analysis prompts usign optional input prompts"""
