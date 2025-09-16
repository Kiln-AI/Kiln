from pathlib import Path

from llama_index.readers.file import PDFReader

from kiln_ai.adapters.extractors.base_extractor import (
    BaseExtractor,
    ExtractionInput,
    ExtractionOutput,
)
from kiln_ai.datamodel.extraction import ExtractorConfig


class LlamaPdfReader(BaseExtractor):
    def __init__(
        self,
        extractor_config: ExtractorConfig,
    ):
        super().__init__(extractor_config)
        self.reader = PDFReader()

    async def _extract(self, extraction_input: ExtractionInput) -> ExtractionOutput:
        if not isinstance(extraction_input.path, Path):
            extraction_input.path = Path(extraction_input.path)

        text = self.reader.load_data(extraction_input.path)

        return ExtractionOutput(
            is_passthrough=False,
            content="\n\n".join([text_i.get_content() for text_i in text]),
            content_format=self.extractor_config.output_format,
        )
