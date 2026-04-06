from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kiln_ai.datamodel.chunk import ChunkerConfig
from kiln_ai.datamodel.document_skill import DocumentSkill
from kiln_ai.datamodel.extraction import (
    Document,
    ExtractorConfig,
    ExtractorType,
    OutputFormat,
)
from kiln_ai.datamodel.project import Project

from app.desktop.studio_server.doc_skill_pipeline import (
    DocSkillProgress,
    DocSkillWorkflowRunner,
    DocSkillWorkflowRunnerConfig,
)

LITELLM_PROPERTIES = {
    "extractor_type": ExtractorType.LITELLM,
    "prompt_document": "Transcribe.",
    "prompt_audio": "Transcribe.",
    "prompt_video": "Transcribe.",
    "prompt_image": "Describe.",
}


@pytest.fixture
def mock_project(tmp_path):
    project_path = tmp_path / "test_project" / "project.kiln"
    project_path.parent.mkdir()
    project = Project(name="Test Project", path=project_path)
    project.save_to_file()
    return project


@pytest.fixture
def extractor_config(mock_project):
    ec = ExtractorConfig(
        name="Test Extractor",
        extractor_type=ExtractorType.LITELLM,
        model_provider_name="gemini_api",
        model_name="gemini-2.0-flash",
        output_format=OutputFormat.MARKDOWN,
        properties=LITELLM_PROPERTIES,
        parent=mock_project,
    )
    ec.save_to_file()
    return ec


@pytest.fixture
def chunker_config(mock_project):
    cc = ChunkerConfig(
        name="Test Chunker",
        chunker_type="fixed_window",
        properties={
            "chunker_type": "fixed_window",
            "chunk_size": 1000,
            "chunk_overlap": 0,
        },
        parent=mock_project,
    )
    cc.save_to_file()
    return cc


@pytest.fixture
def doc_skill(mock_project):
    ds = DocumentSkill(
        name="Test Doc Skill",
        skill_name="test-doc-skill",
        skill_content_header="This skill provides reference documents.",
        extractor_config_id="ext1",
        chunker_config_id="chunk1",
        parent=mock_project,
    )
    ds.save_to_file()
    return ds


@pytest.fixture
def config(doc_skill, mock_project, extractor_config, chunker_config):
    return DocSkillWorkflowRunnerConfig(
        doc_skill=doc_skill,
        project=mock_project,
        extractor_config=extractor_config,
        chunker_config=chunker_config,
    )


def make_mock_document(name, doc_id="doc1", tags=None):
    doc = MagicMock(spec=Document)
    doc.name = name
    doc.name_override = None
    doc.id = doc_id
    doc.tags = tags or []
    return doc


class TestDocSkillProgress:
    def test_defaults(self):
        p = DocSkillProgress()
        assert p.total_document_count == 0
        assert p.total_document_extracted_count == 0
        assert p.total_document_extracted_error_count == 0
        assert p.total_document_chunked_count == 0
        assert p.total_document_chunked_error_count == 0
        assert p.skill_created is False
        assert p.logs is None


class TestGetFilteredDocuments:
    def test_no_tags_returns_all(self, config):
        doc1 = make_mock_document("doc1", doc_id="d1")
        doc2 = make_mock_document("doc2", doc_id="d2")
        config.doc_skill.document_tags = None

        runner = DocSkillWorkflowRunner(config, DocSkillProgress())
        with patch.object(Project, "documents", return_value=[doc1, doc2]):
            result = runner._get_filtered_documents()
        assert len(result) == 2

    def test_tags_filter_documents(self, config):
        doc1 = make_mock_document("doc1", doc_id="d1", tags=["api"])
        doc2 = make_mock_document("doc2", doc_id="d2", tags=["other"])
        config.doc_skill.document_tags = ["api"]

        runner = DocSkillWorkflowRunner(config, DocSkillProgress())
        with patch.object(Project, "documents", return_value=[doc1, doc2]):
            result = runner._get_filtered_documents()
        assert len(result) == 1
        assert result[0].id == "d1"


class TestProgressUpdates:
    def test_extraction_progress_update(self, config):
        runner = DocSkillWorkflowRunner(config, DocSkillProgress())
        from kiln_ai.adapters.rag.rag_runners import RagStepRunnerProgress

        step_progress = RagStepRunnerProgress(success_count=3, error_count=1, logs=[])
        runner._update_extraction_progress(step_progress)
        assert runner.progress.total_document_extracted_count == 3
        assert runner.progress.total_document_extracted_error_count == 1

    def test_chunking_progress_update(self, config):
        runner = DocSkillWorkflowRunner(config, DocSkillProgress())
        from kiln_ai.adapters.rag.rag_runners import RagStepRunnerProgress

        step_progress = RagStepRunnerProgress(success_count=5, error_count=0, logs=[])
        runner._update_chunking_progress(step_progress)
        assert runner.progress.total_document_chunked_count == 5
        assert runner.progress.total_document_chunked_error_count == 0

    def test_extraction_progress_takes_max(self, config):
        runner = DocSkillWorkflowRunner(config, DocSkillProgress())
        runner.progress.total_document_extracted_count = 10
        from kiln_ai.adapters.rag.rag_runners import RagStepRunnerProgress

        step_progress = RagStepRunnerProgress(success_count=3, error_count=0, logs=[])
        runner._update_extraction_progress(step_progress)
        assert runner.progress.total_document_extracted_count == 10


class TestPipelineRun:
    @pytest.mark.asyncio
    async def test_no_documents_raises(self, config):
        runner = DocSkillWorkflowRunner(config, DocSkillProgress())

        progress_list = []
        with patch.object(Project, "documents", return_value=[]):
            with pytest.raises(ValueError, match="No documents found"):
                async for p in runner.run():
                    progress_list.append(p.model_copy())

    @pytest.mark.asyncio
    async def test_full_pipeline_run(self, config):
        doc = make_mock_document("doc.md")

        async def mock_extraction_run(*args, **kwargs):
            from kiln_ai.adapters.rag.rag_runners import RagStepRunnerProgress

            yield RagStepRunnerProgress(success_count=1, error_count=0, logs=[])

        async def mock_chunking_run(*args, **kwargs):
            from kiln_ai.adapters.rag.rag_runners import RagStepRunnerProgress

            yield RagStepRunnerProgress(success_count=1, error_count=0, logs=[])

        mock_skill_builder = MagicMock()
        mock_skill_builder.build = AsyncMock(return_value="skill-123")

        with patch.object(Project, "documents", return_value=[doc]):
            with patch(
                "app.desktop.studio_server.doc_skill_pipeline.RagExtractionStepRunner"
            ) as mock_ext_cls:
                mock_ext_instance = MagicMock()
                mock_ext_instance.run = mock_extraction_run
                mock_ext_cls.return_value = mock_ext_instance

                with patch(
                    "app.desktop.studio_server.doc_skill_pipeline.RagChunkingStepRunner"
                ) as mock_chunk_cls:
                    mock_chunk_instance = MagicMock()
                    mock_chunk_instance.run = mock_chunking_run
                    mock_chunk_cls.return_value = mock_chunk_instance

                    with patch(
                        "app.desktop.studio_server.doc_skill_pipeline.SkillBuilder",
                        return_value=mock_skill_builder,
                    ):
                        runner = DocSkillWorkflowRunner(config, DocSkillProgress())
                        progress_list = []
                        async for p in runner.run():
                            progress_list.append(p.model_copy())

                        assert len(progress_list) >= 3
                        assert progress_list[-1].skill_created is True
                        assert config.doc_skill.skill_id == "skill-123"

    @pytest.mark.asyncio
    async def test_pipeline_sets_document_count(self, config):
        docs = [
            make_mock_document("d1", doc_id="d1"),
            make_mock_document("d2", doc_id="d2"),
        ]

        async def mock_run(*args, **kwargs):
            from kiln_ai.adapters.rag.rag_runners import RagStepRunnerProgress

            yield RagStepRunnerProgress(success_count=2, error_count=0, logs=[])

        mock_skill_builder = MagicMock()
        mock_skill_builder.build = AsyncMock(return_value="skill-456")

        with patch.object(Project, "documents", return_value=docs):
            with patch(
                "app.desktop.studio_server.doc_skill_pipeline.RagExtractionStepRunner"
            ) as mock_ext_cls:
                mock_ext_cls.return_value.run = mock_run

                with patch(
                    "app.desktop.studio_server.doc_skill_pipeline.RagChunkingStepRunner"
                ) as mock_chunk_cls:
                    mock_chunk_cls.return_value.run = mock_run

                    with patch(
                        "app.desktop.studio_server.doc_skill_pipeline.SkillBuilder",
                        return_value=mock_skill_builder,
                    ):
                        runner = DocSkillWorkflowRunner(config, DocSkillProgress())
                        progress_list = []
                        async for p in runner.run():
                            progress_list.append(p.model_copy())

                        found_count_2 = any(
                            p.total_document_count == 2 for p in progress_list
                        )
                        assert found_count_2

    @pytest.mark.asyncio
    async def test_pipeline_tag_filtering(self, config):
        doc1 = make_mock_document("d1", doc_id="d1", tags=["api"])
        doc2 = make_mock_document("d2", doc_id="d2", tags=["other"])
        config.doc_skill.document_tags = ["api"]

        async def mock_run(*args, **kwargs):
            from kiln_ai.adapters.rag.rag_runners import RagStepRunnerProgress

            yield RagStepRunnerProgress(success_count=1, error_count=0, logs=[])

        mock_skill_builder = MagicMock()
        mock_skill_builder.build = AsyncMock(return_value="skill-tags")

        with patch.object(Project, "documents", return_value=[doc1, doc2]):
            with patch(
                "app.desktop.studio_server.doc_skill_pipeline.RagExtractionStepRunner"
            ) as mock_ext_cls:
                mock_ext_cls.return_value.run = mock_run

                with patch(
                    "app.desktop.studio_server.doc_skill_pipeline.RagChunkingStepRunner"
                ) as mock_chunk_cls:
                    mock_chunk_cls.return_value.run = mock_run

                    with patch(
                        "app.desktop.studio_server.doc_skill_pipeline.SkillBuilder",
                        return_value=mock_skill_builder,
                    ):
                        runner = DocSkillWorkflowRunner(config, DocSkillProgress())
                        progress_list = []
                        async for p in runner.run():
                            progress_list.append(p.model_copy())

                        # Only 1 document matches the "api" tag
                        assert any(p.total_document_count == 1 for p in progress_list)

                        # Verify tags were forwarded to extraction runner
                        mock_ext_cls.assert_called_once_with(
                            project=config.project,
                            extractor_config=config.extractor_config,
                            tags=["api"],
                        )

                        # Verify tags were forwarded to chunking runner
                        mock_chunk_cls.assert_called_once_with(
                            project=config.project,
                            extractor_config=config.extractor_config,
                            chunker_config=config.chunker_config,
                            tags=["api"],
                        )
