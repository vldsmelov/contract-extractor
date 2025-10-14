from abc import ABC, abstractmethod
from typing import Dict, Any

class BaseExtractor(ABC):
    @abstractmethod
    async def extract(
        self, text: str, partial: Dict[str, Any], **kwargs: Any
    ) -> Dict[str, Any]:
        ...
