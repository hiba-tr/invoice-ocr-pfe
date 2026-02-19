from abc import ABC, abstractmethod
from PIL import Image

class VLMProcessor(ABC):
    @abstractmethod
    def describe(self, image: Image, prompt: str = None) -> str:
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        pass