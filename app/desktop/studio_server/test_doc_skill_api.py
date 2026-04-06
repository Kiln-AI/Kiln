import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from kiln_ai.datamodel.chunk import ChunkerConfig
from kiln_ai.datamodel.document_skill import DocumentSkill
from kiln_ai.datamodel.extraction import (
    ExtractorConfig,
    ExtractorType,
    OutputFormat,
)
from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.skill import Skill
from kiln_server.custom_errors import connect_custom_errors

from app.desktop.studio_server.doc_skill_api import (
    DocSkillProgress,
    compute_doc_skill_progress,
    connect_doc_skill_api,
)

LITELLM_PROPERTIES = {
    "extractor_type": ExtractorType.LITELLM,
    "prompt_document": "Transcribe.",
    "prompt_audio": "Transcribe.",
    "prompt_video": "Transcribe.",
    "prompt_image": "Describe.",
}


@pytest.fixture
def app():
    test_app = FastAPI()
    connect_custom_errors(test_app)
    connect_doc_skill_api(test_app)
    return test_app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def test_project(tmp_path):
    project_path = tmp_path / "test_project" / "project.kiln"
    project_path.parent.mkdir()
    project = Project(name="Test Project", path=project_path)
    project.save_to_file()
    return project


@pytest.fixture
def mock_project_from_id(test_project):
    with patch(
        "app.desktop.studio_server.doc_skill_api.project_from_id",
        return_value=test_project,
    ) as mock:
        yield mock


@pytest.fixture
def extractor_config(test_project):
    ec = ExtractorConfig(
        name="Test Extractor",
        extractor_type=ExtractorType.LITELLM,
        model_provider_name="gemini_api",
        model_name="gemini-2.0-flash",
        output_format=OutputFormat.MARKDOWN,
        properties=LITELLM_PROPERTIES,
        parent=test_project,
    )
    ec.save_to_file()
    return ec


@pytest.fixture
def chunker_config(test_project):
    cc = ChunkerConfig(
        name="Test Chunker",
        chunker_type="fixed_window",
        properties={
            "chunker_type": "fixed_window",
            "chunk_size": 1000,
            "chunk_overlap": 0,
        },
        parent=test_project,
    )
    cc.save_to_file()
    return cc


@pytest.fixture
def sample_create_request(extractor_config, chunker_config):
    return {
        "name": "My Doc Skill",
        "skill_name": "my-doc-skill",
        "skill_content_header": "These documents contain important reference material.",
        "extractor_config_id": extractor_config.id,
        "chunker_config_id": chunker_config.id,
    }


@pytest.fixture
def saved_doc_skill(test_project, extractor_config, chunker_config):
    ds = DocumentSkill(
        name="Saved Doc Skill",
        skill_name="saved-doc-skill",
        skill_content_header="Saved skill content header.",
        extractor_config_id=extractor_config.id,
        chunker_config_id=chunker_config.id,
        parent=test_project,
    )
    ds.save_to_file()
    return ds


@pytest.fixture
def saved_doc_skill_with_skill(test_project, extractor_config, chunker_config):
    skill = Skill(
        name="generated-skill",
        description="Auto-generated skill.",
        parent=test_project,
    )
    skill.save_to_file()
    skill.save_skill_md("# Generated Skill")

    ds = DocumentSkill(
        name="Complete Doc Skill",
        skill_name="complete-doc-skill",
        skill_content_header="Complete skill content header.",
        extractor_config_id=extractor_config.id,
        chunker_config_id=chunker_config.id,
        skill_id=skill.id,
        parent=test_project,
    )
    ds.save_to_file()
    return ds, skill


class TestCreateDocSkill:
    def test_create_success(
        self, client, test_project, mock_project_from_id, sample_create_request
    ):
        response = client.post(
            f"/api/projects/{test_project.id}/doc_skills",
            json=sample_create_request,
        )
        assert response.status_code == 200
        result = response.json()
        assert result["name"] == "My Doc Skill"
        assert result["skill_name"] == "my-doc-skill"
        assert (
            result["skill_content_header"]
            == sample_create_request["skill_content_header"]
        )
        assert result["skill_id"] is None
        assert result["is_archived"] is False
        assert result["strip_file_extensions"] is True
        assert "id" in result

    def test_create_with_optional_fields(
        self, client, test_project, mock_project_from_id, sample_create_request
    ):
        sample_create_request["description"] = "A description"
        sample_create_request["document_tags"] = ["finance", "reports"]
        sample_create_request["strip_file_extensions"] = False

        response = client.post(
            f"/api/projects/{test_project.id}/doc_skills",
            json=sample_create_request,
        )
        assert response.status_code == 200
        result = response.json()
        assert result["description"] == "A description"
        assert result["document_tags"] == ["finance", "reports"]
        assert result["strip_file_extensions"] is False

    def test_create_missing_required_fields(
        self, client, test_project, mock_project_from_id
    ):
        response = client.post(
            f"/api/projects/{test_project.id}/doc_skills",
            json={"name": "Incomplete"},
        )
        assert response.status_code == 422

    def test_create_invalid_skill_name(
        self, client, test_project, mock_project_from_id, sample_create_request
    ):
        sample_create_request["skill_name"] = "Invalid Name!"
        response = client.post(
            f"/api/projects/{test_project.id}/doc_skills",
            json=sample_create_request,
        )
        assert response.status_code == 422

    def test_create_empty_content_header(
        self, client, test_project, mock_project_from_id, sample_create_request
    ):
        sample_create_request["skill_content_header"] = "   "
        response = client.post(
            f"/api/projects/{test_project.id}/doc_skills",
            json=sample_create_request,
        )
        assert response.status_code == 422

    def test_create_invalid_tags_with_spaces(
        self, client, test_project, mock_project_from_id, sample_create_request
    ):
        sample_create_request["document_tags"] = ["has space"]
        response = client.post(
            f"/api/projects/{test_project.id}/doc_skills",
            json=sample_create_request,
        )
        assert response.status_code == 422


class TestListDocSkills:
    def test_list_empty(self, client, test_project, mock_project_from_id):
        response = client.get(f"/api/projects/{test_project.id}/doc_skills")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_returns_doc_skills(
        self, client, test_project, mock_project_from_id, saved_doc_skill
    ):
        response = client.get(f"/api/projects/{test_project.id}/doc_skills")
        assert response.status_code == 200
        result = response.json()
        assert len(result) == 1
        assert result[0]["name"] == "Saved Doc Skill"
        assert result[0]["skill_name"] == "saved-doc-skill"

    def test_list_includes_archived(
        self, client, test_project, mock_project_from_id, saved_doc_skill
    ):
        saved_doc_skill.is_archived = True
        saved_doc_skill.save_to_file()

        response = client.get(f"/api/projects/{test_project.id}/doc_skills")
        assert response.status_code == 200
        result = response.json()
        assert len(result) == 1
        assert result[0]["is_archived"] is True


class TestGetDocSkill:
    def test_get_found(
        self, client, test_project, mock_project_from_id, saved_doc_skill
    ):
        response = client.get(
            f"/api/projects/{test_project.id}/doc_skills/{saved_doc_skill.id}"
        )
        assert response.status_code == 200
        result = response.json()
        assert result["name"] == "Saved Doc Skill"
        assert result["id"] == saved_doc_skill.id

    def test_get_not_found(self, client, test_project, mock_project_from_id):
        response = client.get(
            f"/api/projects/{test_project.id}/doc_skills/nonexistent-id"
        )
        assert response.status_code == 404


class TestUpdateDocSkill:
    def test_archive(self, client, test_project, mock_project_from_id, saved_doc_skill):
        response = client.patch(
            f"/api/projects/{test_project.id}/doc_skills/{saved_doc_skill.id}",
            json={"is_archived": True},
        )
        assert response.status_code == 200
        assert response.json()["is_archived"] is True

        reloaded = DocumentSkill.from_id_and_parent_path(
            saved_doc_skill.id, test_project.path
        )
        assert reloaded is not None
        assert reloaded.is_archived is True

    def test_archive_cascades_to_skill(
        self,
        client,
        test_project,
        mock_project_from_id,
        saved_doc_skill_with_skill,
    ):
        ds, skill = saved_doc_skill_with_skill
        response = client.patch(
            f"/api/projects/{test_project.id}/doc_skills/{ds.id}",
            json={"is_archived": True},
        )
        assert response.status_code == 200
        assert response.json()["is_archived"] is True

        reloaded_skill = Skill.from_id_and_parent_path(skill.id, test_project.path)
        assert reloaded_skill is not None
        assert reloaded_skill.is_archived is True

    def test_unarchive_restores_both(
        self,
        client,
        test_project,
        mock_project_from_id,
        saved_doc_skill_with_skill,
    ):
        ds, skill = saved_doc_skill_with_skill
        client.patch(
            f"/api/projects/{test_project.id}/doc_skills/{ds.id}",
            json={"is_archived": True},
        )

        response = client.patch(
            f"/api/projects/{test_project.id}/doc_skills/{ds.id}",
            json={"is_archived": False},
        )
        assert response.status_code == 200
        assert response.json()["is_archived"] is False

        reloaded_skill = Skill.from_id_and_parent_path(skill.id, test_project.path)
        assert reloaded_skill is not None
        assert reloaded_skill.is_archived is False

    def test_not_found(self, client, test_project, mock_project_from_id):
        response = client.patch(
            f"/api/projects/{test_project.id}/doc_skills/nonexistent-id",
            json={"is_archived": True},
        )
        assert response.status_code == 404


class TestRunDocSkill:
    def test_already_built(
        self,
        client,
        test_project,
        mock_project_from_id,
        saved_doc_skill_with_skill,
    ):
        ds, _ = saved_doc_skill_with_skill
        response = client.get(f"/api/projects/{test_project.id}/doc_skills/{ds.id}/run")
        assert response.status_code == 422
        assert "already been built" in response.json()["message"]

    def test_archived(
        self, client, test_project, mock_project_from_id, saved_doc_skill
    ):
        saved_doc_skill.is_archived = True
        saved_doc_skill.save_to_file()

        response = client.get(
            f"/api/projects/{test_project.id}/doc_skills/{saved_doc_skill.id}/run"
        )
        assert response.status_code == 422
        assert "archived" in response.json()["message"]

    def test_extractor_not_found(self, client, test_project, mock_project_from_id):
        ds = DocumentSkill(
            name="Bad Config",
            skill_name="bad-config",
            skill_content_header="Content header.",
            extractor_config_id="nonexistent",
            chunker_config_id="nonexistent",
            parent=test_project,
        )
        ds.save_to_file()

        response = client.get(f"/api/projects/{test_project.id}/doc_skills/{ds.id}/run")
        assert response.status_code == 200
        lines = response.text.strip().split("\n")
        data_lines = [line for line in lines if line.startswith("data:")]
        last_data = data_lines[-2]
        parsed = json.loads(last_data.replace("data: ", "", 1))
        assert any(
            "Extractor config not found" in log["message"] for log in parsed["logs"]
        )

    def test_chunker_not_found(
        self,
        client,
        test_project,
        mock_project_from_id,
        extractor_config,
    ):
        ds = DocumentSkill(
            name="Bad Chunker",
            skill_name="bad-chunker",
            skill_content_header="Content header.",
            extractor_config_id=extractor_config.id,
            chunker_config_id="nonexistent",
            parent=test_project,
        )
        ds.save_to_file()

        response = client.get(f"/api/projects/{test_project.id}/doc_skills/{ds.id}/run")
        assert response.status_code == 200
        lines = response.text.strip().split("\n")
        data_lines = [line for line in lines if line.startswith("data:")]
        last_data = data_lines[-2]
        parsed = json.loads(last_data.replace("data: ", "", 1))
        assert any(
            "Chunker config not found" in log["message"] for log in parsed["logs"]
        )

    def test_run_success_sse_format(
        self,
        client,
        test_project,
        mock_project_from_id,
        saved_doc_skill,
    ):
        mock_progress = DocSkillProgress(
            total_document_count=2,
            total_document_extracted_count=2,
            total_document_chunked_count=2,
            skill_created=True,
        )

        async def mock_run(self):
            yield mock_progress

        with patch(
            "app.desktop.studio_server.doc_skill_api._build_workflow_runner"
        ) as mock_build:
            mock_runner = AsyncMock()
            mock_runner.run = lambda: mock_run(mock_runner)
            mock_build.return_value = mock_runner

            response = client.get(
                f"/api/projects/{test_project.id}/doc_skills/{saved_doc_skill.id}/run"
            )

        assert response.status_code == 200
        assert response.headers["content-type"] == "text/event-stream; charset=utf-8"
        lines = response.text.strip().split("\n")
        data_lines = [line for line in lines if line.startswith("data:")]
        assert data_lines[-1] == "data: complete"
        progress_line = data_lines[-2]
        parsed = json.loads(progress_line.replace("data: ", "", 1))
        assert parsed["total_document_count"] == 2
        assert parsed["skill_created"] is True


class TestProgressDocSkill:
    def test_complete_state(
        self,
        client,
        test_project,
        mock_project_from_id,
        saved_doc_skill_with_skill,
    ):
        ds, _ = saved_doc_skill_with_skill
        response = client.post(
            f"/api/projects/{test_project.id}/doc_skills/progress",
            json={"doc_skill_ids": [ds.id]},
        )
        assert response.status_code == 200
        result = response.json()
        assert ds.id in result
        assert result[ds.id]["skill_created"] is True

    def test_pending_state(
        self,
        client,
        test_project,
        mock_project_from_id,
        saved_doc_skill,
    ):
        response = client.post(
            f"/api/projects/{test_project.id}/doc_skills/progress",
            json={"doc_skill_ids": [saved_doc_skill.id]},
        )
        assert response.status_code == 200
        result = response.json()
        assert saved_doc_skill.id in result
        assert result[saved_doc_skill.id]["skill_created"] is False

    def test_all_in_project(
        self,
        client,
        test_project,
        mock_project_from_id,
        saved_doc_skill,
    ):
        response = client.post(
            f"/api/projects/{test_project.id}/doc_skills/progress",
            json={},
        )
        assert response.status_code == 200
        result = response.json()
        assert saved_doc_skill.id in result

    def test_specific_ids_nonexistent(self, client, test_project, mock_project_from_id):
        response = client.post(
            f"/api/projects/{test_project.id}/doc_skills/progress",
            json={"doc_skill_ids": ["nonexistent"]},
        )
        assert response.status_code == 200
        assert response.json() == {}

    def test_empty_ids_list(self, client, test_project, mock_project_from_id):
        response = client.post(
            f"/api/projects/{test_project.id}/doc_skills/progress",
            json={"doc_skill_ids": []},
        )
        assert response.status_code == 200
        assert response.json() == {}


class TestDocSkillSource:
    def test_with_source(
        self,
        client,
        test_project,
        mock_project_from_id,
        saved_doc_skill_with_skill,
    ):
        ds, skill = saved_doc_skill_with_skill
        response = client.get(
            f"/api/projects/{test_project.id}/skills/{skill.id}/doc_skill_source"
        )
        assert response.status_code == 200
        result = response.json()
        assert result["doc_skill_id"] == ds.id
        assert result["doc_skill_name"] == ds.name

    def test_without_source(self, client, test_project, mock_project_from_id):
        skill = Skill(
            name="standalone-skill",
            description="Not from doc skill.",
            parent=test_project,
        )
        skill.save_to_file()

        response = client.get(
            f"/api/projects/{test_project.id}/skills/{skill.id}/doc_skill_source"
        )
        assert response.status_code == 200
        result = response.json()
        assert result["doc_skill_id"] is None
        assert result["doc_skill_name"] is None


class TestComputeDocSkillProgress:
    def test_complete_doc_skill(self, test_project, saved_doc_skill_with_skill):
        ds, _ = saved_doc_skill_with_skill
        progress = compute_doc_skill_progress(test_project, ds)
        assert progress.skill_created is True

    def test_pending_doc_skill_no_docs(self, test_project, saved_doc_skill):
        progress = compute_doc_skill_progress(test_project, saved_doc_skill)
        assert progress.skill_created is False
        assert progress.total_document_count == 0
        assert progress.total_document_extracted_count == 0
        assert progress.total_document_chunked_count == 0


class TestSerializeProgress:
    def test_serialize_format(self):
        from app.desktop.studio_server.doc_skill_api import _serialize_progress
        from kiln_ai.adapters.rag.progress import LogMessage

        progress = DocSkillProgress(
            total_document_count=5,
            total_document_extracted_count=3,
            total_document_extracted_error_count=1,
            total_document_chunked_count=2,
            total_document_chunked_error_count=0,
            skill_created=False,
            logs=[LogMessage(message="Processing...", level="info")],
        )
        result = _serialize_progress(progress)
        assert result["total_document_count"] == 5
        assert result["total_document_extracted_count"] == 3
        assert result["total_document_extracted_error_count"] == 1
        assert result["total_document_chunked_count"] == 2
        assert result["total_document_chunked_error_count"] == 0
        assert result["skill_created"] is False
        assert len(result["logs"]) == 1
        assert result["logs"][0]["message"] == "Processing..."
        assert result["logs"][0]["level"] == "info"

    def test_serialize_no_logs(self):
        from app.desktop.studio_server.doc_skill_api import _serialize_progress

        progress = DocSkillProgress()
        result = _serialize_progress(progress)
        assert result["logs"] == []
