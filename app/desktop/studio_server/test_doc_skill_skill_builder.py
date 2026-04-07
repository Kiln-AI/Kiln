from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kiln_ai.datamodel.chunk import ChunkedDocument, ChunkerConfig
from kiln_ai.datamodel.document_skill import DocumentSkill
from kiln_ai.datamodel.extraction import (
    Extraction,
    ExtractorConfig,
    ExtractorType,
    OutputFormat,
)
from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.skill import Skill

from app.desktop.studio_server.doc_skill_pipeline import DocSkillWorkflowRunnerConfig
from app.desktop.studio_server.doc_skill_skill_builder import SkillBuilder
from app.desktop.studio_server.test_doc_skill_fixtures import (
    LITELLM_PROPERTIES,
    make_mock_document,
)


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


class TestSanitizeName:
    def setup_method(self):
        self.builder = SkillBuilder.__new__(SkillBuilder)

    @pytest.mark.parametrize(
        "input_name,expected",
        [
            ("Hello World", "hello-world"),
            ("file.txt", "file-txt"),
            ("special@#$chars", "special-chars"),
            ("---leading-trailing---", "leading-trailing"),
            ("multiple   spaces", "multiple-spaces"),
            ("UPPERCASE", "uppercase"),
            ("already-valid", "already-valid"),
            ("with_underscore", "with-underscore"),
            ("123numbers", "123numbers"),
        ],
    )
    def test_sanitize_name(self, input_name, expected):
        assert self.builder._sanitize_name(input_name) == expected

    def test_sanitize_name_empty_result(self):
        assert self.builder._sanitize_name("@#$") == "unnamed"

    def test_sanitize_name_unicode(self):
        result = self.builder._sanitize_name("café résumé")
        assert result == "caf-r-sum"


class TestStripFileExtension:
    def setup_method(self):
        self.builder = SkillBuilder.__new__(SkillBuilder)

    @pytest.mark.parametrize(
        "input_name,expected",
        [
            ("file.txt", "file"),
            ("archive.tar.gz", "archive.tar"),
            ("no_extension", "no_extension"),
            (".gitignore", ".gitignore"),
            (".hidden.txt", ".hidden"),
            ("a.b.c.d", "a.b.c.d"),
            ("report.pdf", "report"),
            ("data.json", "data"),
            ("image.jpeg", "image"),
            ("doc.md", "doc"),
            ("file.a", "file.a"),
            ("file.abcde", "file.abcde"),
        ],
    )
    def test_strip_file_extension(self, input_name, expected):
        assert self.builder._strip_file_extension(input_name) == expected


class TestResolveDocumentNames:
    def setup_method(self):
        self.builder = SkillBuilder.__new__(SkillBuilder)
        doc_skill = MagicMock(spec=DocumentSkill)
        doc_skill.strip_file_extensions = True
        self.builder.doc_skill = doc_skill

    def test_basic_resolution(self):
        doc_chunks = {
            "id1": (make_mock_document("report.pdf", doc_id="id1"), ["chunk1"]),
            "id2": (make_mock_document("guide.md", doc_id="id2"), ["chunk2"]),
        }
        result = self.builder._resolve_document_names(doc_chunks)
        assert result == {"id1": "report", "id2": "guide"}

    def test_collision_handling(self):
        doc_chunks = {
            "id1": (make_mock_document("report.pdf", doc_id="id1"), ["chunk1"]),
            "id2": (make_mock_document("Report.pdf", doc_id="id2"), ["chunk2"]),
        }
        result = self.builder._resolve_document_names(doc_chunks)
        names = set(result.values())
        assert "report" in names
        assert "report-2" in names

    def test_triple_collision(self):
        doc_chunks = {
            "id1": (make_mock_document("report.pdf", doc_id="id1"), ["a"]),
            "id2": (make_mock_document("REPORT.txt", doc_id="id2"), ["b"]),
            "id3": (make_mock_document("Report.md", doc_id="id3"), ["c"]),
        }
        result = self.builder._resolve_document_names(doc_chunks)
        names = sorted(result.values())
        assert names == ["report", "report-2", "report-3"]

    def test_name_override(self):
        doc = make_mock_document(
            "original.pdf", doc_id="id1", name_override="Custom Name"
        )
        doc_chunks = {"id1": (doc, ["chunk1"])}
        result = self.builder._resolve_document_names(doc_chunks)
        assert result["id1"] == "custom-name"

    def test_no_extension_stripping(self):
        self.builder.doc_skill.strip_file_extensions = False
        doc_chunks = {
            "id1": (make_mock_document("report.pdf", doc_id="id1"), ["chunk1"]),
        }
        result = self.builder._resolve_document_names(doc_chunks)
        assert result["id1"] == "report-pdf"


class TestBuildSkillMd:
    def setup_method(self):
        self.builder = SkillBuilder.__new__(SkillBuilder)
        doc_skill = MagicMock(spec=DocumentSkill)
        doc_skill.skill_name = "test-skill"
        doc_skill.skill_content_header = "These are reference docs."
        doc_skill.strip_file_extensions = True
        self.builder.doc_skill = doc_skill
        config = MagicMock()
        config.extractor_config = MagicMock()
        config.extractor_config.output_format = OutputFormat.MARKDOWN
        self.builder.config = config

    def test_basic_structure(self):
        doc_chunks = {
            "id1": (make_mock_document("api-guide.md", doc_id="id1"), ["c1", "c2"]),
        }
        doc_names = {"id1": "api-guide"}
        result = self.builder._build_skill_md(doc_names, doc_chunks)

        assert "# Skill: test-skill" in result
        assert "These are reference docs." in result
        assert "## How to Use This Skill" in result
        assert 'skill(name="test-skill"' in result
        assert "## Document Index" in result
        assert "|api-guide|2|`references/api-guide/part[NNN].md`|" in result

    def test_sorted_entries(self):
        doc_chunks = {
            "id2": (make_mock_document("zebra.md", doc_id="id2"), ["c1"]),
            "id1": (make_mock_document("alpha.md", doc_id="id1"), ["c1", "c2"]),
        }
        doc_names = {"id1": "alpha", "id2": "zebra"}
        result = self.builder._build_skill_md(doc_names, doc_chunks)

        alpha_pos = result.index("|alpha|")
        zebra_pos = result.index("|zebra|")
        assert alpha_pos < zebra_pos

    def test_txt_extension(self):
        self.builder.config.extractor_config.output_format = OutputFormat.TEXT
        doc_chunks = {
            "id1": (make_mock_document("doc.txt", doc_id="id1"), ["c1"]),
        }
        doc_names = {"id1": "doc"}
        result = self.builder._build_skill_md(doc_names, doc_chunks)
        assert "part001.txt" in result
        assert "part[NNN].txt" in result


class TestWriteReferenceFiles:
    def setup_method(self):
        self.builder = SkillBuilder.__new__(SkillBuilder)
        config = MagicMock()
        config.extractor_config = MagicMock()
        config.extractor_config.output_format = OutputFormat.MARKDOWN
        self.builder.config = config

    def test_single_chunk(self, tmp_path):
        skill = MagicMock(spec=Skill)
        refs_dir = tmp_path / "references"
        refs_dir.mkdir()
        skill.references_dir.return_value = refs_dir

        doc_chunks = {
            "id1": (make_mock_document("doc.md", doc_id="id1"), ["content here"]),
        }
        doc_names = {"id1": "doc"}
        self.builder._write_reference_files(skill, doc_names, doc_chunks)

        part_file = refs_dir / "doc" / "part001.md"
        assert part_file.exists()
        content = part_file.read_text()
        assert "content here" in content
        assert "<End of Document>" in content

    def test_multiple_chunks_continuation(self, tmp_path):
        skill = MagicMock(spec=Skill)
        refs_dir = tmp_path / "references"
        refs_dir.mkdir()
        skill.references_dir.return_value = refs_dir

        doc_chunks = {
            "id1": (
                make_mock_document("doc.md", doc_id="id1"),
                ["part one", "part two", "part three"],
            ),
        }
        doc_names = {"id1": "doc"}
        self.builder._write_reference_files(skill, doc_names, doc_chunks)

        part1 = (refs_dir / "doc" / "part001.md").read_text()
        assert "<< Document continues in references/doc/part002.md >>" in part1
        assert "<End of Document>" not in part1

        part2 = (refs_dir / "doc" / "part002.md").read_text()
        assert "<< Document continues in references/doc/part003.md >>" in part2

        part3 = (refs_dir / "doc" / "part003.md").read_text()
        assert "<End of Document>" in part3
        assert "<< Document continues" not in part3

    def test_txt_extension(self, tmp_path):
        self.builder.config.extractor_config.output_format = OutputFormat.TEXT

        skill = MagicMock(spec=Skill)
        refs_dir = tmp_path / "references"
        refs_dir.mkdir()
        skill.references_dir.return_value = refs_dir

        doc_chunks = {
            "id1": (make_mock_document("doc.txt", doc_id="id1"), ["content"]),
        }
        doc_names = {"id1": "doc"}
        self.builder._write_reference_files(skill, doc_names, doc_chunks)

        assert (refs_dir / "doc" / "part001.txt").exists()


class TestGenerateSkillDescription:
    def setup_method(self):
        self.builder = SkillBuilder.__new__(SkillBuilder)
        self.builder.doc_skill = MagicMock(spec=DocumentSkill)

    def test_without_tags(self):
        self.builder.doc_skill.document_tags = None
        result = self.builder._generate_skill_description()
        assert result == "A skill providing access to a set of documents."

    def test_with_tags(self):
        self.builder.doc_skill.document_tags = ["api", "docs"]
        result = self.builder._generate_skill_description()
        assert (
            result
            == "A skill providing access to a set of documents tagged 'api', 'docs'"
        )

    def test_with_single_tag(self):
        self.builder.doc_skill.document_tags = ["knowledge_base"]
        result = self.builder._generate_skill_description()
        assert (
            result
            == "A skill providing access to a set of documents tagged 'knowledge_base'"
        )

    def test_long_tags_truncation(self):
        long_tags = [f"very-long-tag-name-{i}" for i in range(100)]
        self.builder.doc_skill.document_tags = long_tags
        result = self.builder._generate_skill_description()
        assert len(result) <= 1024
        assert "100 document tags" in result


class TestMaxPartsValidation:
    @pytest.mark.asyncio
    async def test_exactly_999_parts_ok(self, config):
        builder = SkillBuilder(config, [])
        chunks = ["chunk"] * 999
        doc = make_mock_document("doc.md")
        doc_chunks = {"id1": (doc, chunks)}

        with patch.object(builder, "_collect_document_chunks", return_value=doc_chunks):
            with patch.object(
                builder, "_resolve_document_names", return_value={"id1": "doc"}
            ):
                with patch.object(builder, "_build_skill_md", return_value="# Skill"):
                    with patch.object(
                        builder,
                        "_generate_skill_description",
                        return_value="desc",
                    ):
                        with patch.object(builder, "_write_reference_files"):
                            result = await builder.build()
                            assert result is not None

    @pytest.mark.asyncio
    async def test_1000_parts_raises(self, config):
        builder = SkillBuilder(config, [])
        chunks = ["chunk"] * 1000
        doc = make_mock_document("doc.md")
        doc_chunks = {"id1": (doc, chunks)}

        with patch.object(builder, "_collect_document_chunks", return_value=doc_chunks):
            with pytest.raises(ValueError, match="exceeding the 999 limit"):
                await builder.build()


class TestRollbackOnFailure:
    @pytest.mark.asyncio
    async def test_rollback_deletes_skill_folder(self, config):
        builder = SkillBuilder(config, [])
        doc = make_mock_document("doc.md")
        doc_chunks = {"id1": (doc, ["chunk"])}

        with patch.object(builder, "_collect_document_chunks", return_value=doc_chunks):
            with patch.object(
                builder, "_resolve_document_names", return_value={"id1": "doc"}
            ):
                with patch.object(builder, "_build_skill_md", return_value="# Skill"):
                    with patch.object(
                        builder,
                        "_generate_skill_description",
                        return_value="desc",
                    ):
                        with patch.object(
                            builder,
                            "_write_reference_files",
                            side_effect=RuntimeError("disk full"),
                        ):
                            with patch.object(
                                builder, "_rollback_skill"
                            ) as mock_rollback:
                                with pytest.raises(RuntimeError, match="disk full"):
                                    await builder.build()
                                mock_rollback.assert_called_once()

    def test_rollback_removes_directory(self, tmp_path):
        builder = SkillBuilder.__new__(SkillBuilder)
        skill = MagicMock(spec=Skill)
        skill_dir = tmp_path / "skill_folder"
        skill_dir.mkdir()
        (skill_dir / "skill.kiln").write_text("data")
        skill.path = skill_dir / "skill.kiln"

        builder._rollback_skill(skill)
        assert not skill_dir.exists()

    def test_rollback_noop_when_no_path(self):
        builder = SkillBuilder.__new__(SkillBuilder)
        skill = MagicMock(spec=Skill)
        skill.path = None
        builder._rollback_skill(skill)


class TestCollectDocumentChunks:
    @pytest.mark.asyncio
    async def test_skips_doc_without_extraction(self, config):
        doc = make_mock_document("doc.md")
        doc.extractions = MagicMock(return_value=[])
        builder = SkillBuilder(config, [doc])
        result = await builder._collect_document_chunks()
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_skips_doc_without_chunks(self, config):
        doc = make_mock_document("doc.md")
        extraction = MagicMock(spec=Extraction)
        extraction.extractor_config_id = config.extractor_config.id
        extraction.chunked_documents = MagicMock(return_value=[])
        doc.extractions = MagicMock(return_value=[extraction])
        builder = SkillBuilder(config, [doc])
        result = await builder._collect_document_chunks()
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_skips_empty_chunks(self, config):
        doc = make_mock_document("doc.md")
        extraction = MagicMock(spec=Extraction)
        extraction.extractor_config_id = config.extractor_config.id
        chunked_doc = MagicMock(spec=ChunkedDocument)
        chunked_doc.chunker_config_id = config.chunker_config.id
        chunked_doc.load_chunks_text = AsyncMock(return_value=[])
        extraction.chunked_documents = MagicMock(return_value=[chunked_doc])
        doc.extractions = MagicMock(return_value=[extraction])
        builder = SkillBuilder(config, [doc])
        result = await builder._collect_document_chunks()
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_collects_chunks_successfully(self, config):
        doc = make_mock_document("doc.md")
        extraction = MagicMock(spec=Extraction)
        extraction.extractor_config_id = config.extractor_config.id
        chunked_doc = MagicMock(spec=ChunkedDocument)
        chunked_doc.chunker_config_id = config.chunker_config.id
        chunked_doc.load_chunks_text = AsyncMock(return_value=["text1", "text2"])
        extraction.chunked_documents = MagicMock(return_value=[chunked_doc])
        doc.extractions = MagicMock(return_value=[extraction])
        builder = SkillBuilder(config, [doc])
        result = await builder._collect_document_chunks()
        assert len(result) == 1
        assert result["doc1"][1] == ["text1", "text2"]


class TestBuildEmptyDocChunks:
    @pytest.mark.asyncio
    async def test_no_doc_chunks_raises(self, config):
        builder = SkillBuilder(config, [])
        with patch.object(builder, "_collect_document_chunks", return_value={}):
            with pytest.raises(
                ValueError, match="No documents with extracted and chunked content"
            ):
                await builder.build()


class TestBuildIntegration:
    def _make_builder_with_doc(self, config):
        doc = make_mock_document("report.pdf")
        extraction = MagicMock(spec=Extraction)
        extraction.extractor_config_id = config.extractor_config.id
        chunked_doc = MagicMock(spec=ChunkedDocument)
        chunked_doc.chunker_config_id = config.chunker_config.id
        chunked_doc.load_chunks_text = AsyncMock(
            return_value=["Chapter 1 content", "Chapter 2 content"]
        )
        extraction.chunked_documents = MagicMock(return_value=[chunked_doc])
        doc.extractions = MagicMock(return_value=[extraction])
        return SkillBuilder(config, [doc])

    @pytest.mark.asyncio
    async def test_full_build(self, mock_project, config):
        builder = self._make_builder_with_doc(config)
        skill_id = await builder.build()

        assert skill_id is not None

        skill = Skill.from_id_and_parent_path(skill_id, mock_project.path)
        assert skill is not None
        assert skill.name == "test-doc-skill"
        assert skill.description == "A skill providing access to a set of documents."

        body = skill.body()
        assert "# Skill: test-doc-skill" in body
        assert "## Document Index" in body

        refs_dir = skill.references_dir()
        part1 = (refs_dir / "report" / "part001.md").read_text()
        assert "Chapter 1 content" in part1
        assert "<< Document continues" in part1

        part2 = (refs_dir / "report" / "part002.md").read_text()
        assert "Chapter 2 content" in part2
        assert "<End of Document>" in part2

    @pytest.mark.asyncio
    async def test_user_provided_description_used(self, mock_project, config):
        config.doc_skill.description = "My custom skill description"
        builder = self._make_builder_with_doc(config)
        skill_id = await builder.build()

        skill = Skill.from_id_and_parent_path(skill_id, mock_project.path)
        assert skill.description == "My custom skill description"

    @pytest.mark.asyncio
    async def test_auto_description_when_no_user_description(
        self, mock_project, config
    ):
        config.doc_skill.description = None
        builder = self._make_builder_with_doc(config)
        skill_id = await builder.build()

        skill = Skill.from_id_and_parent_path(skill_id, mock_project.path)
        assert skill.description == "A skill providing access to a set of documents."
