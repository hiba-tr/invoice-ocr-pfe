from abc import ABC, abstractmethod
from typing import List, Dict, Any
from PIL import Image

class LayoutDetector(ABC):
    @abstractmethod
    def detect(self, image: Image) -> List[Dict[str, Any]]:
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        pass