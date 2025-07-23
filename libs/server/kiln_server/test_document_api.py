import io
from unittest.mock import AsyncMock, MagicMock, patch

import anyio
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from kiln_ai.datamodel.basemodel import KilnAttachmentModel
from kiln_ai.datamodel.extraction import (
    Document,
    ExtractorConfig,
    ExtractorType,
    FileInfo,
    Kind,
    OutputFormat,
)
from kiln_ai.datamodel.project import Project

from conftest import MockFileFactoryMimeType
from kiln_server.custom_errors import connect_custom_errors
from kiln_server.document_api import connect_document_api


@pytest.fixture
def app():
    app = FastAPI()
    connect_document_api(app)
    connect_custom_errors(app)
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def project_setup(tmp_path):
    project_path = tmp_path / "test_project" / "project.kiln"
    project_path.parent.mkdir()

    project = Project(name="Test Project", path=project_path)
    project.save_to_file()

    return project


@pytest.fixture
def document_setup(project_setup):
    project = project_setup

    # Create a test document
    test_file_data = b"test file content"
    document = Document(
        parent=project,
        name="test_document",
        description="Test document description",
        kind=Kind.DOCUMENT,
        original_file=FileInfo(
            filename="test.txt",
            mime_type="text/plain",
            attachment=KilnAttachmentModel.from_data(test_file_data, "text/plain"),
            size=len(test_file_data),
        ),
    )
    document.save_to_file()

    return {"project": project, "document": document}


@pytest.fixture
def extractor_config_setup(project_setup):
    project = project_setup

    extractor_config = ExtractorConfig(
        parent=project,
        name="Test Extractor",
        description="Test extractor description",
        output_format=OutputFormat.TEXT,
        passthrough_mimetypes=[OutputFormat.TEXT],
        extractor_type=ExtractorType.LITELLM,
        model_provider_name="gemini_api",
        model_name="gemini-2.0-flash",
        properties={
            "prompt_document": "test-prompt",
            "prompt_video": "test-video-prompt",
            "prompt_audio": "test-audio-prompt",
            "prompt_image": "test-image-prompt",
        },
    )
    extractor_config.save_to_file()

    return {"project": project, "extractor_config": extractor_config}


def check_attachment_saved(document: Document, test_content: bytes):
    if document.path is None:
        raise ValueError("Document path is not set")
    attachment_path = document.original_file.attachment.resolve_path(
        document.path.parent
    )
    assert attachment_path.exists()
    with open(attachment_path, "rb") as f:
        assert f.read() == test_content


@pytest.mark.asyncio
async def test_create_document_success(client, project_setup):
    project = project_setup
    test_content = b"test file content"

    with (
        patch("kiln_server.document_api.ExtractorRunner") as mock_extractor_runner,
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
    ):
        # Create async mock for ExtractorRunner
        mock_project_from_id.return_value = project

        # Create async mock for ExtractorRunner
        mock_runner_instance = AsyncMock()
        mock_runner_instance.run.return_value = iter([])  # Empty async generator
        mock_extractor_runner.return_value = mock_runner_instance

        files = {"file": ("test.txt", io.BytesIO(test_content), "text/plain")}
        data = {"name": "Test Document", "description": "Test description"}

        response = client.post(
            f"/api/projects/{project.id}/documents", files=files, data=data
        )

    assert response.status_code == 200
    result = response.json()
    assert result["id"] is not None
    assert result["name"] == "Test Document"
    assert result["description"] == "Test description"
    assert result["kind"] == "document"
    assert result["original_file"]["filename"] == "test.txt"
    assert result["original_file"]["mime_type"] == "text/plain"
    assert result["original_file"]["size"] == len(test_content)

    # check the attachment was saved with the document
    document = Document.from_id_and_parent_path(result["id"], project.path)
    assert document is not None
    check_attachment_saved(document, test_content)


@pytest.mark.asyncio
async def test_create_document_image_kind(client, project_setup):
    project = project_setup
    test_content = b"fake image content"

    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
        patch("kiln_server.document_api.ExtractorRunner") as mock_extractor_runner,
    ):
        mock_project_from_id.return_value = project

        mock_runner_instance = AsyncMock()
        mock_runner_instance.run.return_value = iter([])
        mock_extractor_runner.return_value = mock_runner_instance

        files = {"file": ("image.jpg", io.BytesIO(test_content), "image/jpeg")}
        data = {"name": "Test Image", "description": "Test image"}

        response = client.post(
            f"/api/projects/{project.id}/documents", files=files, data=data
        )

    assert response.status_code == 200
    result = response.json()
    assert result["kind"] == "image"

    # check the attachment was saved with the document
    document = Document.from_id_and_parent_path(result["id"], project.path)
    assert document is not None
    check_attachment_saved(document, test_content)


@pytest.mark.asyncio
async def test_get_documents_success(client, document_setup):
    project = document_setup["project"]
    document = document_setup["document"]

    with patch("kiln_server.document_api.project_from_id") as mock_project_from_id:
        mock_project = MagicMock()
        mock_project.documents.return_value = [
            document,
        ]
        mock_project_from_id.return_value = mock_project

        response = client.get(f"/api/projects/{project.id}/documents")

    assert response.status_code == 200
    result = response.json()
    assert len(result) == 1
    assert result[0]["id"] == document.id


@pytest.mark.asyncio
async def test_get_document_success(client, document_setup):
    project = document_setup["project"]
    document = document_setup["document"]

    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
        patch(
            "kiln_ai.datamodel.extraction.Document.from_id_and_parent_path"
        ) as mock_document_from_id,
    ):
        mock_document_from_id.return_value = document

        mock_project = MagicMock()
        mock_project.documents.return_value = [document]
        mock_project_from_id.return_value = mock_project

        response = client.get(f"/api/projects/{project.id}/documents/{document.id}")

    assert response.status_code == 200
    result = response.json()
    assert result["id"] == document.id
    assert result["name"] == document.name


@pytest.mark.asyncio
async def test_get_document_not_found(client, project_setup):
    project = project_setup

    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
        patch(
            "kiln_ai.datamodel.extraction.Document.from_id_and_parent_path"
        ) as mock_document_from_id,
    ):
        mock_project_from_id.return_value = project
        mock_document_from_id.return_value = None

        response = client.get(f"/api/projects/{project.id}/documents/fake_id")

    assert response.status_code == 404
    assert "Document not found" in response.json()["message"]


@pytest.mark.asyncio
async def test_edit_tags_add_success(client, document_setup):
    project = document_setup["project"]
    document = document_setup["document"]
    document.tags = ["existing_tag"]

    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
        patch(
            "kiln_ai.datamodel.extraction.Document.from_id_and_parent_path"
        ) as mock_document_from_id,
        patch("kiln_ai.datamodel.extraction.Document.save_to_file") as mock_save,
    ):
        mock_project_from_id.return_value = project
        mock_document_from_id.return_value = document
        mock_save.return_value = None

        response = client.post(
            f"/api/projects/{project.id}/documents/edit_tags",
            json={
                "document_ids": [document.id],
                "add_tags": ["new_tag"],
            },
        )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert "new_tag" in document.tags
    assert "existing_tag" in document.tags


@pytest.mark.asyncio
async def test_edit_tags_remove_success(client, document_setup):
    project = document_setup["project"]
    document = document_setup["document"]
    document.tags = ["tag1", "tag2", "tag_to_remove"]

    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
        patch(
            "kiln_ai.datamodel.extraction.Document.from_id_and_parent_path"
        ) as mock_document_from_id,
        patch("kiln_ai.datamodel.extraction.Document.save_to_file") as mock_save,
    ):
        mock_project_from_id.return_value = project
        mock_document_from_id.return_value = document
        mock_save.return_value = None

        response = client.post(
            f"/api/projects/{project.id}/documents/edit_tags",
            json={
                "document_ids": [document.id],
                "remove_tags": ["tag_to_remove"],
            },
        )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert "tag_to_remove" not in document.tags
    assert "tag1" in document.tags


@pytest.mark.asyncio
async def test_edit_tags_document_not_found(client, project_setup):
    project = project_setup

    with (
        patch("kiln_server.document_api.project_from_id"),
        patch(
            "kiln_ai.datamodel.extraction.Document.from_id_and_parent_path"
        ) as mock_document_from_id,
    ):
        mock_document_from_id.return_value = None

        response = client.post(
            f"/api/projects/{project.id}/documents/edit_tags",
            json={
                "document_ids": ["fake_id"],
                "add_tags": ["new_tag"],
            },
        )

    assert response.status_code == 500
    result = response.json()
    assert "fake_id" in result["message"]["failed_documents"]


@pytest.mark.asyncio
async def test_create_extractor_config_success(client, project_setup):
    project = project_setup

    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
        patch("kiln_ai.datamodel.extraction.ExtractorConfig.save_to_file") as mock_save,
        patch(
            "kiln_server.document_api.built_in_models_from_provider"
        ) as mock_built_in_models_from_provider,
    ):
        mock_project_from_id.return_value = project
        mock_save.return_value = None

        mock_built_in_models_from_provider.return_value = MagicMock(
            supports_doc_extraction=True
        )

        request_data = {
            "name": "Test Extractor",
            "description": "Test description",
            "output_format": "text/plain",
            "passthrough_mimetypes": ["text/plain"],
            "model_provider_name": "gemini_api",
            "model_name": "gemini-2.0-flash",
            "properties": {
                "prompt_document": "test-prompt",
                "prompt_video": "test-video-prompt",
                "prompt_audio": "test-audio-prompt",
                "prompt_image": "test-image-prompt",
            },
        }

        response = client.post(
            f"/api/projects/{project.id}/create_extractor_config", json=request_data
        )

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["name"] == "Test Extractor"
    assert result["description"] == "Test description"
    assert result["output_format"] == "text/plain"
    assert result["extractor_type"] == "litellm"
    assert result["passthrough_mimetypes"] == ["text/plain"]
    assert result["model_provider_name"] == "gemini_api"
    assert result["model_name"] == "gemini-2.0-flash"
    assert result["properties"]["prompt_document"] == "test-prompt"
    assert result["properties"]["prompt_video"] == "test-video-prompt"
    assert result["properties"]["prompt_audio"] == "test-audio-prompt"
    assert result["properties"]["prompt_image"] == "test-image-prompt"


@pytest.mark.asyncio
async def test_get_extractor_configs_success(client, extractor_config_setup):
    project = extractor_config_setup["project"]
    extractor_config = extractor_config_setup["extractor_config"]

    with patch("kiln_server.document_api.project_from_id") as mock_project_from_id:
        mock_project = MagicMock()
        mock_project.extractor_configs = MagicMock(return_value=[extractor_config])
        mock_project_from_id.return_value = mock_project

        response = client.get(f"/api/projects/{project.id}/extractor_configs")

    assert response.status_code == 200
    result = response.json()
    assert len(result) == 1
    assert result[0]["id"] == extractor_config.id


@pytest.mark.asyncio
async def test_get_extractor_config_success(client, extractor_config_setup):
    project = extractor_config_setup["project"]
    extractor_config = extractor_config_setup["extractor_config"]

    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
        patch(
            "kiln_ai.datamodel.extraction.ExtractorConfig.from_id_and_parent_path"
        ) as mock_from_id,
    ):
        mock_project_from_id.return_value = project
        mock_from_id.return_value = extractor_config

        response = client.get(
            f"/api/projects/{project.id}/extractor_configs/{extractor_config.id}"
        )

    assert response.status_code == 200
    result = response.json()
    assert result["id"] == extractor_config.id


@pytest.mark.asyncio
async def test_get_extractor_config_not_found(client, project_setup):
    project = project_setup

    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
        patch(
            "kiln_ai.datamodel.extraction.ExtractorConfig.from_id_and_parent_path"
        ) as mock_from_id,
    ):
        mock_project_from_id.return_value = project
        mock_from_id.return_value = None

        response = client.get(f"/api/projects/{project.id}/extractor_configs/fake_id")

    assert response.status_code == 404
    assert "Extractor config not found" in response.json()["message"]


@pytest.mark.asyncio
async def test_patch_extractor_config_success(client, extractor_config_setup):
    project = extractor_config_setup["project"]
    extractor_config = extractor_config_setup["extractor_config"]

    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
        patch(
            "kiln_ai.datamodel.extraction.ExtractorConfig.from_id_and_parent_path"
        ) as mock_from_id,
        patch("kiln_ai.datamodel.extraction.ExtractorConfig.save_to_file") as mock_save,
    ):
        mock_project_from_id.return_value = project
        mock_from_id.return_value = extractor_config
        mock_save.return_value = None

        patch_data = {
            "name": "Updated Extractor Name",
            "description": "Updated description",
            "is_archived": True,
        }

        response = client.patch(
            f"/api/projects/{project.id}/extractor_configs/{extractor_config.id}",
            json=patch_data,
        )

    assert response.status_code == 200
    assert extractor_config.name == "Updated Extractor Name"
    assert extractor_config.description == "Updated description"
    assert extractor_config.is_archived is True


@pytest.mark.asyncio
async def test_delete_document_success(client, document_setup):
    project = document_setup["project"]
    document = document_setup["document"]

    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
        patch(
            "kiln_ai.datamodel.extraction.Document.from_id_and_parent_path"
        ) as mock_from_id,
        patch("kiln_ai.datamodel.extraction.Document.delete") as mock_delete,
    ):
        mock_project_from_id.return_value = project
        mock_from_id.return_value = document
        mock_delete.return_value = None

        response = client.delete(f"/api/projects/{project.id}/documents/{document.id}")

    assert response.status_code == 200
    result = response.json()
    assert document.id in result["message"]


@pytest.mark.asyncio
async def test_delete_documents_success(client, document_setup):
    project = document_setup["project"]
    document = document_setup["document"]

    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
        patch(
            "kiln_ai.datamodel.extraction.Document.from_id_and_parent_path"
        ) as mock_from_id,
        patch("kiln_ai.datamodel.extraction.Document.delete") as mock_delete,
    ):
        mock_project_from_id.return_value = project
        mock_from_id.return_value = document
        mock_delete.return_value = None

        response = client.post(
            f"/api/projects/{project.id}/documents/delete", json=[document.id]
        )

    assert response.status_code == 200
    result = response.json()
    assert document.id in result["message"]


@pytest.mark.parametrize(
    "filename,expected_content_type,expected_kind",
    [
        ("document.pdf", "application/pdf", "document"),
        ("document.txt", "text/plain", "document"),
        ("document.md", "text/markdown", "document"),
        ("document.html", "text/html", "document"),
        ("image.png", "image/png", "image"),
        ("image.jpeg", "image/jpeg", "image"),
        ("video.mp4", "video/mp4", "video"),
        ("video.mov", "video/quicktime", "video"),
        ("audio.mp3", "audio/mpeg", "audio"),
        ("audio.wav", "audio/wav", "audio"),
        ("audio.ogg", "audio/ogg", "audio"),
    ],
)
@pytest.mark.asyncio
async def test_create_document_content_type_detection(
    client, project_setup, filename, expected_content_type, expected_kind
):
    project = project_setup
    test_content = b"test content"

    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
        patch("kiln_ai.datamodel.extraction.Document.save_to_file") as mock_save,
        patch("kiln_server.document_api.ExtractorRunner") as mock_extractor_runner,
    ):
        mock_project_from_id.return_value = project
        mock_save.return_value = None

        mock_runner_instance = AsyncMock()
        mock_runner_instance.run.return_value = iter([])
        mock_extractor_runner.return_value = mock_runner_instance

        files = {"file": (filename, io.BytesIO(test_content), expected_content_type)}
        data = {"name": "Test File", "description": "Test description"}

        response = client.post(
            f"/api/projects/{project.id}/documents", files=files, data=data
        )

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["kind"] == expected_kind
    assert result["original_file"]["mime_type"] == expected_content_type


@pytest.mark.asyncio
async def test_create_document_filetype_not_supported(
    client, project_setup, mock_file_factory
):
    project = project_setup
    test_content = await anyio.Path(
        mock_file_factory(MockFileFactoryMimeType.CSV)
    ).read_bytes()

    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
    ):
        mock_project_from_id.return_value = project

        files = {
            "file": (
                "file.csv",
                io.BytesIO(test_content),
                "text/csv",
            )
        }
        data = {"name": "Test File", "description": "Test description"}

        response = client.post(
            f"/api/projects/{project.id}/documents", files=files, data=data
        )

    assert response.status_code == 422, response.text
    assert "Unsupported mime type: text/csv" in response.json()["message"]


@pytest.mark.asyncio
async def test_create_extractor_config_model_not_found(client, project_setup):
    project = project_setup

    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
        patch(
            "kiln_server.document_api.built_in_models_from_provider"
        ) as mock_built_in_models_from_provider,
    ):
        mock_project_from_id.return_value = project
        mock_built_in_models_from_provider.return_value = None

        response = client.post(
            f"/api/projects/{project.id}/create_extractor_config",
            json={
                "name": "Test Extractor",
                "description": "Test description",
                "output_format": "text/plain",
                "passthrough_mimetypes": ["text/plain"],
                "model_provider_name": "openai",
                "model_name": "fake_model",
            },
        )

    assert response.status_code == 422, response.text
    assert "Model fake_model not found" in response.json()["message"]


@pytest.mark.asyncio
async def test_create_extractor_config_model_invalid_provider_name(
    client, project_setup
):
    project = project_setup

    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
    ):
        mock_project_from_id.return_value = project

        response = client.post(
            f"/api/projects/{project.id}/create_extractor_config",
            json={
                "name": "Test Extractor",
                "description": "Test description",
                "output_format": "text/plain",
                "passthrough_mimetypes": ["text/plain"],
                "model_provider_name": "fake_provider",
                "model_name": "fake_model",
            },
        )

    # the error occurs during validation of request payload
    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_create_extractor_config_model_not_supported_for_extraction(
    client, project_setup
):
    project = project_setup

    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
        patch(
            "kiln_server.document_api.built_in_models_from_provider"
        ) as mock_built_in_models_from_provider,
    ):
        mock_project_from_id.return_value = project
        mock_built_in_models_from_provider.return_value = MagicMock()
        mock_built_in_models_from_provider.return_value.supports_doc_extraction = False

        response = client.post(
            f"/api/projects/{project.id}/create_extractor_config",
            json={
                "name": "Test Extractor",
                "description": "Test description",
                "output_format": "text/plain",
                "passthrough_mimetypes": ["text/plain"],
                "model_provider_name": "openai",
                "model_name": "fake_model",
            },
        )

    assert response.status_code == 422, response.text
    assert (
        "Model fake_model does not support document extraction"
        in response.json()["message"]
    )
