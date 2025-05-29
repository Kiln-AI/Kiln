import logging
import mimetypes
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncGenerator, List

from kiln_ai.adapters.extractors.base_extractor import BaseExtractor, FileInfo
from kiln_ai.adapters.extractors.registry import extractor_adapter_from_type
from kiln_ai.datamodel.basemodel import KilnAttachmentModel
from kiln_ai.datamodel.document import Document
from kiln_ai.datamodel.extraction import Extraction, ExtractionSource, ExtractorConfig
from kiln_ai.utils.async_job_runner import AsyncJobRunner, Progress

logger = logging.getLogger(__name__)


# TODO: refactor this logic into the KilnAttachmentModel as a classmethod (e.g. from_string(xxx) -> KilnAttachmentModel)
def to_attachment(data: str, mime_type: str) -> KilnAttachmentModel:
    # mimetype to extension
    extension = mimetypes.guess_extension(mime_type) or ".unknown"

    # write to temp file
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=extension)
    temp_file.write(data.encode("utf-8"))
    temp_file.close()
    return KilnAttachmentModel(
        path=Path(temp_file.name),
    )


@dataclass
class ExtractorJob:
    item: Document
    extractor_config: ExtractorConfig


class ExtractorRunner:
    def __init__(
        self,
        documents: List[Document],
        extractor_configs: List[ExtractorConfig],
    ):
        if len(extractor_configs) == 0:
            raise ValueError("Extractor runner requires at least one extractor config")

        self.documents = documents
        self.extractor_configs = extractor_configs

    def collect_jobs(self) -> List[ExtractorJob]:
        return [
            ExtractorJob(
                item=document,
                extractor_config=extractor_config,
            )
            for document in self.documents
            for extractor_config in self.extractor_configs
        ]

    async def run(self, concurrency: int = 25) -> AsyncGenerator[Progress, None]:
        jobs = self.collect_jobs()

        runner = AsyncJobRunner(concurrency=concurrency)
        async for progress in runner.run(jobs, self.run_job):
            yield progress

    async def run_job(self, job: ExtractorJob) -> bool:
        try:
            extractor_factory = extractor_adapter_from_type(
                job.extractor_config.extractor_type,
            )
            extractor = extractor_factory(job.extractor_config)
            if not isinstance(extractor, BaseExtractor):
                raise ValueError("Not able to create extractor from extractor config")

            output = extractor.extract(
                # TODO: guess the mimetype upstream, so here we would already have it
                FileInfo(path=job.item.original_file.attachment.path)
            )

            # TODO: turn output into an attachment and save
            extraction = Extraction(
                parent=job.item,
                extractor_config_id=job.extractor_config.id,
                output=to_attachment(output.content, output.content_format),
                # TODO: harmonize between ExtractionSource and output property
                source=ExtractionSource.PASSTHROUGH
                if output.is_passthrough
                else ExtractionSource.PROCESSED,
            )

            extraction.save_to_file()

            return True
        except Exception as e:
            logger.error(f"Error running eval job for dataset item {job.item.id}: {e}")
            return False
