import logging
import mimetypes
from abc import ABC, abstractmethod
from pathlib import Path

from pydantic import BaseModel, Field

from kiln_ai.datamodel.extraction import ExtractorConfig, OutputFormat

logger = logging.getLogger(__name__)


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
    async def _extract(self, path: Path, mime_type: str) -> ExtractionOutput:
        pass

    async def extract(
        self,
        path: Path | str,
        mime_type: str | None = None,
    ) -> ExtractionOutput:
        """
        Extracts content from a file by delegating to the concrete extractor implementation.
        """
        if isinstance(path, str):
            path = Path(path)

        try:
            if mime_type is None:
                mime_type, _ = mimetypes.guess_type(path)
                if mime_type is None:
                    raise ValueError(f"Unable to guess file mime type for {path}")

            if self._should_passthrough(mime_type):
                return ExtractionOutput(
                    is_passthrough=True,
                    content=path.read_text(encoding="utf-8"),
                    content_format=self.extractor_config.output_format,
                )

            return await self._extract(
                path=path,
                mime_type=mime_type,
            )
        except Exception as e:
            raise ValueError(f"Error extracting {path}: {e}") from e

    def _should_passthrough(self, mime_type: str) -> bool:
        return mime_type.lower() in {
            mt.lower() for mt in self.extractor_config.passthrough_mimetypes
        }
