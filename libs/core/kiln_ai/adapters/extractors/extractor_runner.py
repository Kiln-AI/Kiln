import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import AsyncGenerator, Dict, List, Set

from kiln_ai.adapters.extractors.base_extractor import BaseExtractor
from kiln_ai.adapters.extractors.registry import extractor_adapter_from_type
from kiln_ai.datamodel.basemodel import ID_TYPE, KilnAttachmentModel
from kiln_ai.datamodel.extraction import (
    Document,
    Extraction,
    ExtractionSource,
    ExtractorConfig,
)
from kiln_ai.utils.async_job_runner import AsyncJobRunner, Progress

logger = logging.getLogger(__name__)


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
        # all extractor configs come from the same project
        project = self.extractor_configs[0].parent_project()
        if project is None:
            raise ValueError("Extractor runner requires a project")

        # filter out documents that have already been extracted for this extractor config
        already_extracted: Dict[ID_TYPE, Set[ID_TYPE]] = defaultdict(set)
        for document in project.documents():
            for extraction in document.extractions():
                already_extracted[extraction.extractor_config_id].add(document.id)

        jobs = []
        for extractor_config in self.extractor_configs:
            # queue up unprocessed documents for this extractor config
            for document in self.documents:
                if document.id in already_extracted.get(extractor_config.id, []):
                    continue
                jobs.append(
                    ExtractorJob(
                        item=document,
                        extractor_config=extractor_config,
                    )
                )

        return jobs

    async def run(self, concurrency: int = 25) -> AsyncGenerator[Progress, None]:
        jobs = self.collect_jobs()

        runner = AsyncJobRunner(concurrency=concurrency)
        async for progress in runner.run(jobs, self.run_job):
            yield progress

    async def run_job(self, job: ExtractorJob) -> bool:
        try:
            extractor = extractor_adapter_from_type(
                job.extractor_config.extractor_type,
                job.extractor_config,
            )
            if not isinstance(extractor, BaseExtractor):
                raise ValueError("Not able to create extractor from extractor config")

            if job.item.path is None:
                raise ValueError("Document path is not set")

            output = extractor.extract(
                path=job.item.original_file.attachment.resolve_path(
                    job.item.path.parent
                ),
                mime_type=job.item.original_file.mime_type,
            )

            extraction = Extraction(
                parent=job.item,
                extractor_config_id=job.extractor_config.id,
                output=KilnAttachmentModel.from_data(
                    data=output.content,
                    mime_type=output.content_format,
                ),
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
