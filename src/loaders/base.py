from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Union

class BaseLoader(ABC):
    @abstractmethod
    def load(self, file_path: Path) -> List[Union[str, 'PIL.Image.Image']]:
        pass

    @abstractmethod
    def get_type(self) -> str:
        pass

    @abstractmethod
    def supports(self, file_ext: str, mime_type: str = None) -> bool:
        pass