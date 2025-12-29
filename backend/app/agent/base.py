"""
Base classes for investigation tools.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any
from pydantic import BaseModel


class BaseTool(ABC):
    """Base class for all investigation tools."""

    def __init__(self):
        self.name = self.__class__.__name__

    @abstractmethod
    async def execute(self, **kwargs) -> BaseModel:
        """Execute the tool with given parameters and return structured output."""
        pass

    def _use_mock(self, api_key: str) -> bool:
        """Determine if mock data should be used."""
        return not api_key or api_key == ""
