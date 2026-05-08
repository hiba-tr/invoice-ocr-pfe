from typing import Annotated, Literal, Optional, Union
from pydantic import BaseModel, Field, SecretStr


class BaseBackendOptions(BaseModel):
    enable_remote_fetch: bool = False
    enable_local_fetch: bool = False


class DeclarativeBackendOptions(BaseBackendOptions):
    kind: Literal["declarative"] = Field("declarative", exclude=True, repr=False)


class PdfBackendOptions(BaseBackendOptions):
    kind: Literal["pdf"] = Field("pdf", exclude=True, repr=False)
    password: Optional[SecretStr] = None


BackendOptions = Annotated[
    Union[
        DeclarativeBackendOptions,
        PdfBackendOptions,
    ],
    Field(discriminator="kind"),
]