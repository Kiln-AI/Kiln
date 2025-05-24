import logging
import mimetypes
import pathlib
from abc import ABC, abstractmethod

from pydantic import BaseModel, Field

from kiln_ai.datamodel.extraction import ExtractorConfig, OutputFormat

logger = logging.getLogger(__name__)


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
    content_format: OutputFormat = Field(
        description="The format of the extracted data."
    )
    content: str = Field(description="The extracted data.")


class BaseExtractor(ABC):
    """
    Base class for all extractors.

    Should be subclassed by each extractor.
    """

    def __init__(self, extractor_config: ExtractorConfig):
        self.extractor_config = extractor_config

    @abstractmethod
    def _extract(self, file_info: FileInfoInternal) -> ExtractionOutput:
        pass

    def extract(
        self,
        file_info: FileInfo,
    ) -> ExtractionOutput:
        """
        Extracts content from a file by delegating to the concrete extractor implementation.
        """
        try:
            mime_type, _ = mimetypes.guess_type(file_info.path)
            if mime_type is None:
                raise ValueError("Unable to guess file mime type")

            if self._should_passthrough(mime_type):
                return ExtractionOutput(
                    is_passthrough=True,
                    content=pathlib.Path(file_info.path).read_text(encoding="utf-8"),
                    content_format=self.extractor_config.output_format,
                )

            return self._extract(
                FileInfoInternal(
                    path=file_info.path,
                    mime_type=mime_type,
                ),
            )
        except Exception as e:
            raise ValueError(f"Error extracting {file_info.path}: {e}") from e

    def _should_passthrough(self, mime_type: str) -> bool:
        return mime_type.lower() in {
            mt.lower() for mt in self.extractor_config.passthrough_mimetypes
        }
