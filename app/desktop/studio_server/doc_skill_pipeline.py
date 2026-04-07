import logging
from dataclasses import dataclass
from typing import AsyncGenerator

from kiln_ai.adapters.rag.deduplication import filter_documents_by_tags
from kiln_ai.adapters.rag.progress import LogMessage
from kiln_ai.adapters.rag.rag_runners import (
    LOCK_TIMEOUT_SECONDS,
    RagChunkingStepRunner,
    RagExtractionStepRunner,
    RagStepRunnerProgress,
)
from kiln_ai.datamodel.chunk import ChunkerConfig
from kiln_ai.datamodel.document_skill import DocumentSkill
from kiln_ai.datamodel.extraction import Document, ExtractorConfig
from kiln_ai.datamodel.project import Project
from kiln_ai.utils.lock import shared_async_lock_manager
from pydantic import BaseModel

from .doc_skill_skill_builder import SkillBuilder

logger = logging.getLogger(__name__)


class DocSkillProgress(BaseModel):
    total_document_count: int = 0
    total_document_extracted_count: int = 0
    total_document_extracted_error_count: int = 0
    total_document_chunked_count: int = 0
    total_document_chunked_error_count: int = 0
    skill_created: bool = False
    logs: list[LogMessage] | None = None


@dataclass
class DocSkillWorkflowRunnerConfig:
    doc_skill: DocumentSkill
    project: Project
    extractor_config: ExtractorConfig
    chunker_config: ChunkerConfig


class DocSkillWorkflowRunner:
    def __init__(
        self,
        config: DocSkillWorkflowRunnerConfig,
        initial_progress: DocSkillProgress,
    ):
        self.config = config
        self.progress = initial_progress
        self._lock_key = f"doc_skill:run:{config.doc_skill.id}"

    def _get_filtered_documents(self) -> list[Document]:
        all_docs = self.config.project.documents(readonly=True)
        tags = self.config.doc_skill.document_tags
        if tags is None:
            return all_docs
        return filter_documents_by_tags(all_docs, tags)

    def _update_extraction_progress(self, step_progress: RagStepRunnerProgress) -> None:
        if step_progress.success_count is not None:
            self.progress.total_document_extracted_count = max(
                self.progress.total_document_extracted_count,
                step_progress.success_count,
            )
        if step_progress.error_count is not None:
            self.progress.total_document_extracted_error_count = (
                step_progress.error_count
            )
        self.progress.logs = step_progress.logs

    def _update_chunking_progress(self, step_progress: RagStepRunnerProgress) -> None:
        if step_progress.success_count is not None:
            self.progress.total_document_chunked_count = max(
                self.progress.total_document_chunked_count,
                step_progress.success_count,
            )
        if step_progress.error_count is not None:
            self.progress.total_document_chunked_error_count = step_progress.error_count
        self.progress.logs = step_progress.logs

    async def run(self) -> AsyncGenerator[DocSkillProgress, None]:
        yield self.progress

        async with shared_async_lock_manager.acquire(
            self._lock_key, timeout=LOCK_TIMEOUT_SECONDS
        ):
            documents = self._get_filtered_documents()
            if not documents:
                raise ValueError("No documents found with the selected tags.")

            self.progress.total_document_count = len(documents)
            yield self.progress

            extraction_runner = RagExtractionStepRunner(
                project=self.config.project,
                extractor_config=self.config.extractor_config,
                tags=self.config.doc_skill.document_tags,
            )
            async for step_progress in extraction_runner.run():
                self._update_extraction_progress(step_progress)
                yield self.progress

            chunking_runner = RagChunkingStepRunner(
                project=self.config.project,
                extractor_config=self.config.extractor_config,
                chunker_config=self.config.chunker_config,
                tags=self.config.doc_skill.document_tags,
            )
            async for step_progress in chunking_runner.run():
                self._update_chunking_progress(step_progress)
                yield self.progress

            skill_builder = SkillBuilder(self.config, documents)
            skill_id = await skill_builder.build()

            self.config.doc_skill.skill_id = skill_id
            self.config.doc_skill.save_to_file()

            self.progress.skill_created = True
            yield self.progress
