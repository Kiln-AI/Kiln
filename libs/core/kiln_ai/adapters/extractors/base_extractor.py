import logging
from abc import ABC, abstractmethod
from pathlib import Path

from pydantic import BaseModel, Field

from kiln_ai.datamodel.extraction import ExtractorConfig, OutputFormat

logger = logging.getLogger(__name__)


class ExtractionInput(BaseModel):
    path: Path | str = Field(description="The absolute path to the file to extract.")
    mime_type: str = Field(description="The mime type of the file.")


class ExtractionOutput(BaseModel):
    """
    The output of an extraction. This is the data that will be saved to the data store.
    """

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
    async def _extract(self, extraction_input: ExtractionInput) -> ExtractionOutput:
        pass

    async def extract(
        self,
        extraction_input: ExtractionInput,
    ) -> ExtractionOutput:
        """
        Extracts content from a file by delegating to the concrete extractor implementation.
        """
        try:
            if self._should_passthrough(extraction_input.mime_type):
                return ExtractionOutput(
                    is_passthrough=True,
                    content=Path(extraction_input.path).read_text(encoding="utf-8"),
                    content_format=self.extractor_config.output_format,
                )

            return await self._extract(
                extraction_input,
            )
        except Exception as e:
            raise ValueError(f"Error extracting {extraction_input.path}: {e}") from e

    def _should_passthrough(self, mime_type: str) -> bool:
        return mime_type.lower() in {
            mt.lower() for mt in self.extractor_config.passthrough_mimetypes
        }

    def output_format(self) -> OutputFormat:
        return self.extractor_config.output_format

    @abstractmethod
    async def clear_cache_for_file_path(self, file_path: Path) -> None:
        pass
