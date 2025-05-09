import logging
from abc import ABC, abstractmethod
from enum import Enum

from pydantic import BaseModel, Field, model_validator
from typing_extensions import Self

import kiln_ai.adapters.extractors.file_utils as file_utils

logger = logging.getLogger(__name__)


class ExtractionFormat(str, Enum):
    TEXT = "text/plain"
    MARKDOWN = "text/markdown"


class BaseExtractorConfig(BaseModel):
    """
    Base class for all extractor configs.
    """

    passthrough_mimetypes: list[str] = Field(
        default_factory=list,
        description="If the mimetype is in this list, the extractor will not be used and the text content of the file will be returned as is. Only text mime types are supported for passthrough.",
    )

    output_format: ExtractionFormat = Field(
        default=ExtractionFormat.MARKDOWN,
        description="The format to use for the output.",
    )

    @model_validator(mode="after")
    def validate_passthrough_mime_types(self) -> Self:
        # we keep a whitelist here because some mimetypes would not make sense as passthrough
        # e.g. image/png is not a text format
        allowed_mime_type_prefixes = [
            "text/",
        ]

        for mime_type in self.passthrough_mimetypes:
            if not any(
                mime_type.startswith(prefix) for prefix in allowed_mime_type_prefixes
            ):
                raise ValueError(
                    f"Mime type {mime_type} is not allowed for passthrough. Allowed mime type prefixes are {', '.join(allowed_mime_type_prefixes)}."
                )
        return self


# TODO: take in the file/document datamodel instead once we have it
class FileInfo(BaseModel):
    # TODO: check if works with relative paths or needs to be absolute
    path: str = Field(description="The path to the file to extract from.")


class FileInfoInternal(FileInfo):
    mime_type: str = Field(description="The mime type of the file to extract from.")


class ExtractionOutput(BaseModel):
    is_passthrough: bool = Field(
        default=False, description="Whether the extractor returned the file as is."
    )
    content_format: ExtractionFormat = Field(
        description="The format of the extracted data."
    )
    content: str = Field(description="The extracted data.")


class BaseExtractor(ABC):
    """
    Base class for all extractors.

    Should be subclassed, and the _extract method implemented.
    """

    def __init__(self, config: BaseExtractorConfig):
        self.config = config

    @abstractmethod
    def _extract(
        self, file_info: FileInfoInternal, custom_prompt: str | None
    ) -> ExtractionOutput:
        pass

    def extract(
        self,
        file_info: FileInfoInternal,
        custom_prompt: str | None,
    ) -> ExtractionOutput:
        try:
            mime_type = self._get_mime_type(file_info.path)
            if self._should_passthrough(mime_type):
                return ExtractionOutput(
                    is_passthrough=True,
                    content=self._load_file_text(file_info.path),
                    content_format=self.config.output_format,
                )
            return self._extract(
                FileInfoInternal(
                    path=file_info.path,
                    mime_type=mime_type,
                ),
                custom_prompt,
            )
        except Exception as e:
            raise ValueError(f"Error extracting {file_info.path}: {e}")

    def _should_passthrough(self, mime_type: str) -> bool:
        """
        Whether the extractor should return the file as is.
        """
        return mime_type in self.config.passthrough_mimetypes

    def _load_file_bytes(self, path: str) -> bytes:
        try:
            return file_utils.load_file_bytes(path)
        except Exception as e:
            raise ValueError(f"Error loading file bytes for {path}: {e}")

    def _load_file_text(self, path: str) -> str:
        try:
            return file_utils.load_file_text(path)
        except Exception as e:
            raise ValueError(f"Error loading file text for {path}: {e}")

    def _get_mime_type(self, path: str) -> str:
        # NOTE: maybe we will already have the mimetype from the datamodel? but not sure
        # we would trust it anyway in the extractor, will need to check
        try:
            return file_utils.get_mime_type(path)
        except Exception as e:
            raise ValueError(f"Error getting mime type for {path}: {e}")
