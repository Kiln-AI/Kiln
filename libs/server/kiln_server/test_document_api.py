import io
from pathlib import Path
from unittest.mock import MagicMock, patch

import anyio
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from kiln_ai.adapters.ml_embedding_model_list import EmbeddingModelName
from kiln_ai.datamodel.basemodel import KilnAttachmentModel
from kiln_ai.datamodel.chunk import ChunkerConfig, ChunkerType
from kiln_ai.datamodel.datamodel_enums import ModelProviderName
from kiln_ai.datamodel.embedding import EmbeddingConfig
from kiln_ai.datamodel.extraction import (
    Document,
    ExtractorConfig,
    ExtractorType,
    FileInfo,
    Kind,
    OutputFormat,
)
from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.rag import RagConfig

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
def mock_project(tmp_path):
    project_path = tmp_path / "test_project" / "project.kiln"
    project_path.parent.mkdir()

    project = Project(name="Test Project", path=project_path)
    project.save_to_file()

    return project


@pytest.fixture
def mock_extractor_config(mock_project):
    extractor_config = ExtractorConfig(
        parent=mock_project,
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
    return extractor_config


@pytest.fixture
def mock_chunker_config(mock_project):
    chunker_config = ChunkerConfig(
        parent=mock_project,
        name="Test Chunker",
        description="Test chunker description",
        chunker_type=ChunkerType.FIXED_WINDOW,
        properties={
            "chunk_size": 100,
            "chunk_overlap": 10,
        },
    )
    chunker_config.save_to_file()
    return chunker_config


@pytest.fixture
def mock_embedding_config(mock_project):
    embedding_config = EmbeddingConfig(
        parent=mock_project,
        name="Test Embedding",
        description="Test embedding description",
        model_provider_name=ModelProviderName.openai,
        model_name=EmbeddingModelName.openai_text_embedding_3_small,
        properties={},
    )
    embedding_config.save_to_file()
    return embedding_config


@pytest.fixture
def mock_document(mock_project):
    project = mock_project

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
def extractor_config_setup(mock_project):
    project = mock_project

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
async def test_create_document_success(client, mock_project):
    project = mock_project
    test_content = b"test file content"

    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
        patch(
            "kiln_server.document_api.run_all_extractors_and_rag_workflows_no_wait"
        ) as mock_run_workflows,
    ):
        mock_project_from_id.return_value = project
        mock_run_workflows.return_value = None

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

    # check that we triggered the workflows
    mock_run_workflows.assert_called_once()


@pytest.mark.asyncio
async def test_create_document_image_kind(client, mock_project, mock_file_factory):
    project = mock_project
    test_image_file = mock_file_factory(MockFileFactoryMimeType.JPEG)
    test_image_file_bytes = Path(test_image_file).read_bytes()
    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
        patch(
            "kiln_server.document_api.run_all_extractors_and_rag_workflows_no_wait"
        ) as mock_run_workflows,
    ):
        mock_project_from_id.return_value = project
        mock_run_workflows.return_value = None

        files = {"file": ("image.jpg", io.BytesIO(test_image_file_bytes), "image/jpeg")}
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
    check_attachment_saved(document, test_image_file_bytes)

    # check that we triggered the workflows
    mock_run_workflows.assert_called_once()


@pytest.mark.asyncio
async def test_get_documents_success(client, mock_document):
    project = mock_document["project"]
    document = mock_document["document"]

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
async def test_get_document_success(client, mock_document):
    project = mock_document["project"]
    document = mock_document["document"]

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
async def test_get_document_not_found(client, mock_project):
    project = mock_project

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
async def test_edit_tags_add_success(client, mock_document):
    project = mock_document["project"]
    document = mock_document["document"]
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
async def test_edit_tags_remove_success(client, mock_document):
    project = mock_document["project"]
    document = mock_document["document"]
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
async def test_edit_tags_document_not_found(client, mock_project):
    project = mock_project

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
async def test_create_extractor_config_success(client, mock_project):
    project = mock_project

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
async def test_get_extractor_config_not_found(client, mock_project):
    project = mock_project

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
async def test_delete_document_success(client, mock_document):
    project = mock_document["project"]
    document = mock_document["document"]

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
async def test_delete_documents_success(client, mock_document):
    project = mock_document["project"]
    document = mock_document["document"]

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
    client, mock_project, filename, expected_content_type, expected_kind
):
    project = mock_project
    test_content = b"test content"

    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
        patch("kiln_ai.datamodel.extraction.Document.save_to_file") as mock_save,
        patch(
            "kiln_server.document_api.run_all_extractors_and_rag_workflows_no_wait"
        ) as mock_run_workflows,
    ):
        mock_project_from_id.return_value = project
        mock_save.return_value = None
        mock_run_workflows.return_value = None

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
    client, mock_project, mock_file_factory
):
    project = mock_project
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


# test for create chunker config
@pytest.mark.asyncio
async def test_create_chunker_config_success(client, mock_project):
    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
    ):
        mock_project_from_id.return_value = mock_project

        response = client.post(
            f"/api/projects/{mock_project.id}/create_chunker_config",
            json={
                "name": "Test Chunker Config",
                "description": "Test Chunker Config description",
                "chunker_type": "fixed_window",
                "properties": {
                    "chunk_size": 100,
                    "chunk_overlap": 10,
                },
            },
        )

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["id"] is not None
    assert result["name"] == "Test Chunker Config"
    assert result["description"] == "Test Chunker Config description"
    assert result["chunker_type"] == "fixed_window"
    assert result["properties"]["chunk_size"] == 100
    assert result["properties"]["chunk_overlap"] == 10


@pytest.mark.asyncio
async def test_create_chunker_config_invalid_chunker_type(client, mock_project):
    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
    ):
        mock_project_from_id.return_value = mock_project
        response = client.post(
            f"/api/projects/{mock_project.id}/create_chunker_config",
            json={
                "name": "Test Chunker Config",
                "description": "Test Chunker Config description",
                "chunker_type": "invalid_chunker_type",
                "properties": {
                    "chunk_size": 100,
                    "chunk_overlap": 10,
                },
            },
        )

    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_create_extractor_config_model_not_found(client, mock_project):
    project = mock_project

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
    client, mock_project
):
    project = mock_project

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
async def test_get_chunker_configs_success(client, mock_project, mock_chunker_config):
    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
    ):
        mock_project_from_id.return_value = mock_project
        response = client.get(f"/api/projects/{mock_project.id}/chunker_configs")

    assert response.status_code == 200, response.text
    result = response.json()
    assert len(result) == 1
    assert result[0]["id"] == mock_chunker_config.id


@pytest.mark.parametrize(
    "model_provider_name,model_name",
    [
        ("openai", "openai_text_embedding_3_small"),
        ("openai", "openai_text_embedding_3_large"),
        ("gemini_api", "gemini_text_embedding_004"),
    ],
)
@pytest.mark.asyncio
async def test_create_embedding_config_success(
    client, mock_project, model_provider_name, model_name
):
    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
    ):
        mock_project_from_id.return_value = mock_project
        response = client.post(
            f"/api/projects/{mock_project.id}/create_embedding_config",
            json={
                "name": "Test Embedding Config",
                "description": "Test Embedding Config description",
                "model_provider_name": model_provider_name,
                "model_name": model_name,
                "properties": {},
            },
        )

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["id"] is not None
    assert result["name"] == "Test Embedding Config"
    assert result["description"] == "Test Embedding Config description"
    assert result["model_provider_name"] == model_provider_name
    assert result["model_name"] == model_name
    assert result["properties"] == {}


@pytest.mark.asyncio
async def test_create_embedding_config_invalid_model_provider_name(
    client, mock_project
):
    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
    ):
        mock_project_from_id.return_value = mock_project
        response = client.post(
            f"/api/projects/{mock_project.id}/create_embedding_config",
            json={
                "name": "Test Embedding Config",
                "description": "Test Embedding Config description",
                "model_provider_name": "invalid_model_provider_name",
                "model_name": "openai_text_embedding_3_small",
                "properties": {},
            },
        )

    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_get_embedding_configs_success(
    client, mock_project, mock_embedding_config
):
    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
    ):
        mock_project_from_id.return_value = mock_project
        response = client.get(f"/api/projects/{mock_project.id}/embedding_configs")

    assert response.status_code == 200, response.text
    result = response.json()
    assert len(result) == 1
    assert result[0]["id"] == mock_embedding_config.id


@pytest.mark.asyncio
async def test_create_rag_config_success(
    client,
    mock_project,
    mock_extractor_config,
    mock_chunker_config,
    mock_embedding_config,
):
    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
    ):
        mock_project_from_id.return_value = mock_project
        response = client.post(
            f"/api/projects/{mock_project.id}/rag_configs/create_rag_config",
            json={
                "name": "Test RAG Config",
                "description": "Test RAG Config description",
                "extractor_config_id": mock_extractor_config.id,
                "chunker_config_id": mock_chunker_config.id,
                "embedding_config_id": mock_embedding_config.id,
            },
        )

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["id"] is not None
    assert result["name"] == "Test RAG Config"
    assert result["description"] == "Test RAG Config description"
    assert result["extractor_config_id"] is not None
    assert result["chunker_config_id"] is not None
    assert result["embedding_config_id"] is not None


@pytest.mark.parametrize(
    "missing_config_type",
    ["extractor_config_id", "chunker_config_id", "embedding_config_id"],
)
@pytest.mark.asyncio
async def test_create_rag_config_missing_config(
    client,
    mock_project,
    mock_extractor_config,
    mock_chunker_config,
    mock_embedding_config,
    missing_config_type,
):
    project = mock_project

    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
    ):
        mock_project_from_id.return_value = mock_project

        payload = {
            "name": "Test RAG Config",
            "description": "Test RAG Config description",
            "extractor_config_id": mock_extractor_config.id,
            "chunker_config_id": mock_chunker_config.id,
            "embedding_config_id": mock_embedding_config.id,
        }

        # set one of the configs to a fake id - where we expect the error to be thrown
        payload[missing_config_type] = "fake_id"

        response = client.post(
            f"/api/projects/{project.id}/rag_configs/create_rag_config",
            json=payload,
        )

    assert response.status_code == 404
    assert "fake_id not found" in response.json()["message"]


@pytest.mark.asyncio
async def test_get_rag_configs_success(
    client,
    mock_project,
    mock_extractor_config,
    mock_chunker_config,
    mock_embedding_config,
):
    # create a rag config
    rag_configs = [
        RagConfig(
            parent=mock_project,
            name="Test RAG Config 1",
            description="Test RAG Config 1 description",
            extractor_config_id=mock_extractor_config.id,
            chunker_config_id=mock_chunker_config.id,
            embedding_config_id=mock_embedding_config.id,
        ),
        RagConfig(
            parent=mock_project,
            name="Test RAG Config 2",
            description="Test RAG Config 2 description",
            extractor_config_id=mock_extractor_config.id,
            chunker_config_id=mock_chunker_config.id,
            embedding_config_id=mock_embedding_config.id,
        ),
        RagConfig(
            parent=mock_project,
            name="Test RAG Config 3",
            description="Test RAG Config 3 description",
            extractor_config_id=mock_extractor_config.id,
            chunker_config_id=mock_chunker_config.id,
            embedding_config_id=mock_embedding_config.id,
        ),
    ]

    for rag_config in rag_configs:
        rag_config.save_to_file()

    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
    ):
        mock_project_from_id.return_value = mock_project
        response = client.get(f"/api/projects/{mock_project.id}/rag_configs")

    assert response.status_code == 200, response.text
    result = response.json()
    assert len(result) == len(rag_configs)

    for response_rag_config, rag_config in zip(
        sorted(result, key=lambda x: x["id"]),
        sorted(rag_configs, key=lambda x: str(x.id)),
    ):
        assert response_rag_config["id"] == rag_config.id
        assert response_rag_config["name"] == rag_config.name
        assert response_rag_config["description"] == rag_config.description
        assert (
            response_rag_config["extractor_config"]["id"]
            == rag_config.extractor_config_id
        )
        assert (
            response_rag_config["chunker_config"]["id"] == rag_config.chunker_config_id
        )
        assert (
            response_rag_config["embedding_config"]["id"]
            == rag_config.embedding_config_id
        )


@pytest.mark.asyncio
async def test_get_rag_config_success(
    client,
    mock_project,
    mock_extractor_config,
    mock_chunker_config,
    mock_embedding_config,
):
    rag_config = RagConfig(
        parent=mock_project,
        name="Test RAG Config",
        description="Test RAG Config description",
        extractor_config_id=mock_extractor_config.id,
        chunker_config_id=mock_chunker_config.id,
        embedding_config_id=mock_embedding_config.id,
    )
    rag_config.save_to_file()

    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
    ):
        mock_project_from_id.return_value = mock_project
        response = client.get(
            f"/api/projects/{mock_project.id}/rag_configs/{rag_config.id}"
        )

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["id"] == rag_config.id
    assert result["name"] == rag_config.name
    assert result["description"] == rag_config.description
    assert result["extractor_config"]["id"] == rag_config.extractor_config_id
    assert result["chunker_config"]["id"] == rag_config.chunker_config_id
    assert result["embedding_config"]["id"] == rag_config.embedding_config_id


@pytest.mark.asyncio
async def test_get_rag_config_not_found(client, mock_project):
    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
    ):
        mock_project_from_id.return_value = mock_project
        response = client.get(f"/api/projects/{mock_project.id}/rag_configs/fake_id")

    assert response.status_code == 404, response.text
    assert "RAG config not found" in response.json()["message"]


@pytest.mark.asyncio
async def test_create_extractor_config_model_not_supported_for_extraction(
    client, mock_project
):
    project = mock_project

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
