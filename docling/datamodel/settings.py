import sys
from pathlib import Path
from typing import Annotated, Optional, Tuple

from pydantic import BaseModel, PlainValidator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _validate_page_range(v: Tuple[int, int]) -> Tuple[int, int]:
    if v[0] < 1 or v[1] < v[0]:
        raise ValueError("Invalid page range")
    return v


PageRange = Annotated[Tuple[int, int], PlainValidator(_validate_page_range)]
DEFAULT_PAGE_RANGE: PageRange = (1, sys.maxsize)


class DocumentLimits(BaseModel):
    max_num_pages: int = sys.maxsize
    max_file_size: int = sys.maxsize
    page_range: PageRange = DEFAULT_PAGE_RANGE


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DOCLING_"
    )

    limits: DocumentLimits = DocumentLimits()

    cache_dir: Path = Path.home() / ".cache" / "docling"
    artifacts_path: Optional[Path] = None


settings = AppSettings()