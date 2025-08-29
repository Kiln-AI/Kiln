import io
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import anyio
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient
from kiln_ai.adapters.ml_embedding_model_list import EmbeddingModelName
from kiln_ai.adapters.rag.progress import LogMessage, RagProgress
from kiln_ai.adapters.vector_store.base_vector_store_adapter import SearchResult
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
from kiln_ai.datamodel.vector_store import VectorStoreConfig, VectorStoreType

from conftest import MockFileFactoryMimeType
from kiln_server.custom_errors import connect_custom_errors
from kiln_server.document_api import (
    connect_document_api,
    run_rag_workflow_runner_with_status,
)


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
def mock_vector_store_config(mock_project, tmp_path):
    vector_store_config = VectorStoreConfig(
        id="kiln:vector_store:lancedb",
        parent=mock_project,
        name="Test Vector Store",
        store_type=VectorStoreType.LANCE_DB_FTS,
        properties={
            "similarity_top_k": 10,
            "overfetch_factor": 20,
            "vector_column_name": "vector",
            "text_key": "text",
            "doc_id_key": "doc_id",
        },
    )
    vector_store_config.save_to_file()
    return vector_store_config


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


@pytest.mark.parametrize("chunk_size,chunk_overlap", [(10, 10), (10, 20)])
async def test_create_chunker_config_invalid_chunk_size(
    client, mock_project, chunk_size, chunk_overlap
):
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
                    "chunk_size": chunk_size,
                    "chunk_overlap": chunk_overlap,
                },
            },
        )

    assert response.status_code == 422, response.text
    assert "Chunk overlap must be less than chunk size" in response.json()["message"]


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


@pytest.mark.asyncio
async def test_get_chunker_configs_no_chunker_configs(client, mock_project):
    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
    ):
        mock_project_from_id.return_value = mock_project
        response = client.get(f"/api/projects/{mock_project.id}/chunker_configs")

    assert response.status_code == 200, response.text
    result = response.json()
    assert len(result) == 0


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


@pytest.mark.parametrize("model_dimensions,custom_dimensions", [(100, -1), (100, 101)])
async def test_create_embedding_config_invalid_dimensions(
    client, mock_project, model_dimensions, custom_dimensions
):
    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
        patch(
            "kiln_server.document_api.built_in_embedding_models_from_provider"
        ) as mock_built_in_embedding_models_from_provider,
    ):
        mock_project_from_id.return_value = mock_project
        mock_built_in_embedding_models_from_provider.return_value = MagicMock()
        mock_built_in_embedding_models_from_provider.return_value.n_dimensions = (
            model_dimensions
        )
        response = client.post(
            f"/api/projects/{mock_project.id}/create_embedding_config",
            json={
                "name": "Test Embedding Config",
                "description": "Test Embedding Config description",
                "model_provider_name": "openai",
                "model_name": "openai_text_embedding_3_small",
                "properties": {
                    "dimensions": custom_dimensions,
                },
            },
        )

    assert response.status_code == 422, response.text
    assert (
        "Dimensions must be a positive integer and less than the model's dimensions"
        in response.json()["message"]
    )


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
async def test_get_embedding_configs_no_embedding_configs(client, mock_project):
    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
    ):
        mock_project_from_id.return_value = mock_project
        response = client.get(f"/api/projects/{mock_project.id}/embedding_configs")

    assert response.status_code == 200, response.text
    result = response.json()
    assert len(result) == 0


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
    mock_vector_store_config,
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
            vector_store_config_id=mock_vector_store_config.id,
        ),
        RagConfig(
            parent=mock_project,
            name="Test RAG Config 2",
            description="Test RAG Config 2 description",
            extractor_config_id=mock_extractor_config.id,
            chunker_config_id=mock_chunker_config.id,
            embedding_config_id=mock_embedding_config.id,
            vector_store_config_id=mock_vector_store_config.id,
        ),
        RagConfig(
            parent=mock_project,
            name="Test RAG Config 3",
            description="Test RAG Config 3 description",
            extractor_config_id=mock_extractor_config.id,
            chunker_config_id=mock_chunker_config.id,
            embedding_config_id=mock_embedding_config.id,
            vector_store_config_id=mock_vector_store_config.id,
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
    mock_vector_store_config,
):
    rag_config = RagConfig(
        parent=mock_project,
        name="Test RAG Config",
        description="Test RAG Config description",
        extractor_config_id=mock_extractor_config.id,
        chunker_config_id=mock_chunker_config.id,
        embedding_config_id=mock_embedding_config.id,
        vector_store_config_id=mock_vector_store_config.id,
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


@pytest.mark.asyncio
async def test_run_rag_config_success(
    client,
    mock_project,
    mock_extractor_config,
    mock_chunker_config,
    mock_embedding_config,
    mock_vector_store_config,
):
    # Create a rag config
    rag_config = RagConfig(
        parent=mock_project,
        name="Test RAG Config",
        description="Test RAG Config description",
        extractor_config_id=mock_extractor_config.id,
        chunker_config_id=mock_chunker_config.id,
        embedding_config_id=mock_embedding_config.id,
        vector_store_config_id=mock_vector_store_config.id,
    )
    rag_config.save_to_file()

    mock_runner = MagicMock()
    mock_streaming_response = MagicMock()

    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
        patch(
            "kiln_server.document_api.build_rag_workflow_runner"
        ) as mock_build_runner,
        patch(
            "kiln_server.document_api.run_rag_workflow_runner_with_status"
        ) as mock_run_runner,
        patch("kiln_ai.utils.lock.shared_async_lock_manager") as mock_lock_manager,
    ):
        mock_project_from_id.return_value = mock_project
        mock_build_runner.return_value = mock_runner
        mock_run_runner.return_value = mock_streaming_response
        mock_lock_manager.acquire.return_value.__aenter__ = AsyncMock()
        mock_lock_manager.acquire.return_value.__aexit__ = AsyncMock()

        response = client.get(
            f"/api/projects/{mock_project.id}/rag_configs/{rag_config.id}/run"
        )

    assert response.status_code == 200
    mock_build_runner.assert_called_once_with(mock_project, str(rag_config.id))
    mock_run_runner.assert_called_once_with(mock_runner)


@pytest.mark.asyncio
async def test_run_rag_config_not_found(client, mock_project):
    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
        patch(
            "kiln_server.document_api.build_rag_workflow_runner"
        ) as mock_build_runner,
    ):
        mock_project_from_id.return_value = mock_project
        mock_build_runner.side_effect = HTTPException(
            status_code=404, detail="RAG config not found"
        )

        response = client.get(
            f"/api/projects/{mock_project.id}/rag_configs/fake_id/run"
        )

    assert response.status_code == 404
    assert "RAG config not found" in response.json()["message"]


@pytest.mark.asyncio
async def test_run_rag_config_missing_configs(
    client,
    mock_project,
    mock_extractor_config,
    mock_chunker_config,
    mock_embedding_config,
    mock_vector_store_config,
):
    # Create a rag config with missing configs
    rag_config = RagConfig(
        parent=mock_project,
        name="Test RAG Config",
        description="Test RAG Config description",
        extractor_config_id=mock_extractor_config.id,
        chunker_config_id=mock_chunker_config.id,
        embedding_config_id=mock_embedding_config.id,
        vector_store_config_id=mock_vector_store_config.id,
    )
    rag_config.save_to_file()

    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
        patch(
            "kiln_server.document_api.build_rag_workflow_runner"
        ) as mock_build_runner,
    ):
        mock_project_from_id.return_value = mock_project
        mock_build_runner.side_effect = HTTPException(
            status_code=400, detail="RAG config is missing required configs"
        )

        response = client.get(
            f"/api/projects/{mock_project.id}/rag_configs/{rag_config.id}/run"
        )

    assert response.status_code == 400
    assert "RAG config is missing required configs" in response.json()["message"]


@pytest.mark.asyncio
async def test_get_rag_config_progress_specific_configs(
    client,
    mock_project,
    mock_extractor_config,
    mock_chunker_config,
    mock_embedding_config,
    mock_vector_store_config,
):
    # Create rag configs
    rag_configs = [
        RagConfig(
            parent=mock_project,
            name="Test RAG Config 1",
            description="Test RAG Config 1 description",
            extractor_config_id=mock_extractor_config.id,
            chunker_config_id=mock_chunker_config.id,
            embedding_config_id=mock_embedding_config.id,
            vector_store_config_id=mock_vector_store_config.id,
        ),
        RagConfig(
            parent=mock_project,
            name="Test RAG Config 2",
            description="Test RAG Config 2 description",
            extractor_config_id=mock_extractor_config.id,
            chunker_config_id=mock_chunker_config.id,
            embedding_config_id=mock_embedding_config.id,
            vector_store_config_id=mock_vector_store_config.id,
        ),
    ]

    for rag_config in rag_configs:
        rag_config.save_to_file()

    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
        patch(
            "kiln_server.document_api.compute_current_progress_for_rag_configs"
        ) as mock_compute_progress,
    ):
        mock_project_from_id.return_value = mock_project

        # Mock the progress computation
        expected_progress = {
            str(rag_configs[0].id): RagProgress(
                total_document_count=5,
                total_document_completed_count=3,
                total_document_extracted_count=3,
                total_document_chunked_count=2,
                total_document_embedded_count=1,
            ),
            str(rag_configs[1].id): RagProgress(
                total_document_count=5,
                total_document_completed_count=2,
                total_document_extracted_count=2,
                total_document_chunked_count=1,
                total_document_embedded_count=0,
            ),
        }
        mock_compute_progress.return_value = expected_progress

        response = client.post(
            f"/api/projects/{mock_project.id}/rag_configs/progress",
            json={"rag_config_ids": [str(rag_configs[0].id), str(rag_configs[1].id)]},
        )

    assert response.status_code == 200
    result = response.json()
    assert len(result) == 2
    assert str(rag_configs[0].id) in result
    assert str(rag_configs[1].id) in result
    assert result[str(rag_configs[0].id)]["total_document_count"] == 5
    assert result[str(rag_configs[0].id)]["total_document_completed_count"] == 3
    assert result[str(rag_configs[1].id)]["total_document_count"] == 5
    assert result[str(rag_configs[1].id)]["total_document_completed_count"] == 2

    mock_compute_progress.assert_called_once()
    call_args = mock_compute_progress.call_args
    assert call_args[0][0] == mock_project
    assert len(call_args[0][1]) == 2
    assert call_args[0][1][0].id == rag_configs[0].id
    assert call_args[0][1][1].id == rag_configs[1].id


@pytest.mark.asyncio
async def test_get_rag_config_progress_all_configs(
    client,
    mock_project,
    mock_extractor_config,
    mock_chunker_config,
    mock_embedding_config,
    mock_vector_store_config,
):
    # Create rag configs
    rag_configs = [
        RagConfig(
            parent=mock_project,
            name="Test RAG Config 1",
            description="Test RAG Config 1 description",
            extractor_config_id=mock_extractor_config.id,
            chunker_config_id=mock_chunker_config.id,
            embedding_config_id=mock_embedding_config.id,
            vector_store_config_id=mock_vector_store_config.id,
        ),
        RagConfig(
            parent=mock_project,
            name="Test RAG Config 2",
            description="Test RAG Config 2 description",
            extractor_config_id=mock_extractor_config.id,
            chunker_config_id=mock_chunker_config.id,
            embedding_config_id=mock_embedding_config.id,
            vector_store_config_id=mock_vector_store_config.id,
        ),
    ]

    for rag_config in rag_configs:
        rag_config.save_to_file()

    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
        patch(
            "kiln_server.document_api.compute_current_progress_for_rag_configs"
        ) as mock_compute_progress,
        patch(
            "kiln_ai.datamodel.project.Project.rag_configs", return_value=rag_configs
        ),
    ):
        mock_project_from_id.return_value = mock_project

        # Mock the progress computation
        expected_progress = {
            str(rag_configs[0].id): RagProgress(
                total_document_count=5,
                total_document_completed_count=3,
                total_document_extracted_count=3,
                total_document_chunked_count=2,
                total_document_embedded_count=1,
            ),
            str(rag_configs[1].id): RagProgress(
                total_document_count=5,
                total_document_completed_count=2,
                total_document_extracted_count=2,
                total_document_chunked_count=1,
                total_document_embedded_count=0,
            ),
        }
        mock_compute_progress.return_value = expected_progress

        response = client.post(
            f"/api/projects/{mock_project.id}/rag_configs/progress",
            json={"rag_config_ids": None},
        )

    assert response.status_code == 200
    result = response.json()
    assert len(result) == 2
    assert str(rag_configs[0].id) in result
    assert str(rag_configs[1].id) in result

    mock_compute_progress.assert_called_once()
    call_args = mock_compute_progress.call_args
    assert call_args[0][0] == mock_project
    assert len(call_args[0][1]) == 2
    assert call_args[0][1][0].id == rag_configs[0].id
    assert call_args[0][1][1].id == rag_configs[1].id


@pytest.mark.asyncio
async def test_get_rag_config_progress_empty_list(
    client,
    mock_project,
    mock_extractor_config,
    mock_chunker_config,
    mock_embedding_config,
):
    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
        patch(
            "kiln_server.document_api.compute_current_progress_for_rag_configs"
        ) as mock_compute_progress,
    ):
        mock_project_from_id.return_value = mock_project
        mock_compute_progress.return_value = {}

        response = client.post(
            f"/api/projects/{mock_project.id}/rag_configs/progress",
            json={"rag_config_ids": []},
        )

    assert response.status_code == 200
    result = response.json()
    assert result == {}


@pytest.mark.asyncio
async def test_get_rag_config_progress_invalid_config_id(
    client,
    mock_project,
    mock_extractor_config,
    mock_chunker_config,
    mock_embedding_config,
    mock_vector_store_config,
):
    # Create a valid rag config
    rag_config = RagConfig(
        parent=mock_project,
        name="Test RAG Config",
        description="Test RAG Config description",
        extractor_config_id=mock_extractor_config.id,
        chunker_config_id=mock_chunker_config.id,
        embedding_config_id=mock_embedding_config.id,
        vector_store_config_id=mock_vector_store_config.id,
    )
    rag_config.save_to_file()

    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
        patch(
            "kiln_server.document_api.compute_current_progress_for_rag_configs"
        ) as mock_compute_progress,
    ):
        mock_project_from_id.return_value = mock_project

        # Mock the progress computation - should only return progress for valid config
        expected_progress = {
            str(rag_config.id): RagProgress(
                total_document_count=5,
                total_document_completed_count=3,
                total_document_extracted_count=3,
                total_document_chunked_count=2,
                total_document_embedded_count=1,
            ),
        }
        mock_compute_progress.return_value = expected_progress

        response = client.post(
            f"/api/projects/{mock_project.id}/rag_configs/progress",
            json={"rag_config_ids": [str(rag_config.id), "fake_id"]},
        )

    assert response.status_code == 200
    result = response.json()
    assert len(result) == 1
    assert str(rag_config.id) in result
    assert "fake_id" not in result


@pytest.mark.asyncio
async def test_run_rag_workflow_runner_with_status_success():
    """Test successful execution of run_rag_workflow_runner_with_status"""

    # Create mock progress objects
    log_message = LogMessage(level="info", message="Processing documents...")

    progress_updates = [
        RagProgress(
            total_document_count=5,
            total_document_completed_count=0,
            total_document_extracted_count=2,
            total_document_chunked_count=1,
            total_document_embedded_count=0,
            logs=[log_message],
        ),
        RagProgress(
            total_document_count=5,
            total_document_completed_count=0,
            total_document_extracted_count=4,
            total_document_chunked_count=3,
            total_document_embedded_count=1,
            logs=[log_message],
        ),
        RagProgress(
            total_document_count=5,
            total_document_completed_count=5,
            total_document_extracted_count=5,
            total_document_chunked_count=5,
            total_document_embedded_count=5,
            logs=[log_message],
        ),
    ]

    # Create a simple async generator for the mock runner
    async def mock_run():
        for progress in progress_updates:
            yield progress

    # Create mock runner
    mock_runner = MagicMock()
    mock_runner.run.return_value = mock_run()

    # Call the function
    response = await run_rag_workflow_runner_with_status(mock_runner)

    # Verify response type
    assert isinstance(response, StreamingResponse)
    assert response.media_type == "text/event-stream"

    # Read the streaming content
    content = ""
    async for chunk in response.body_iterator:
        content += str(chunk)

    # Parse the SSE content
    lines = content.strip().split("\n")

    # Should have 4 data events (3 progress updates + 1 complete)
    data_lines = [line for line in lines if line.startswith("data: ")]
    assert len(data_lines) == 4

    # Check the progress data
    for i, data_line in enumerate(data_lines[:-1]):  # Exclude the last "complete" line
        json_str = data_line[6:]  # Remove "data: " prefix
        data = json.loads(json_str)

        expected_progress = progress_updates[i]
        assert data["total_document_count"] == expected_progress.total_document_count
        assert (
            data["total_document_completed_count"]
            == expected_progress.total_document_completed_count
        )
        assert (
            data["total_document_extracted_count"]
            == expected_progress.total_document_extracted_count
        )
        assert (
            data["total_document_chunked_count"]
            == expected_progress.total_document_chunked_count
        )
        assert (
            data["total_document_embedded_count"]
            == expected_progress.total_document_embedded_count
        )
        assert len(data["logs"]) == 1
        assert data["logs"][0]["message"] == "Processing documents..."
        assert data["logs"][0]["level"] == "info"

    # Check the final complete message
    assert data_lines[-1] == "data: complete"


@pytest.mark.parametrize("logs", [None, []])
@pytest.mark.asyncio
async def test_run_rag_workflow_runner_with_status_no_logs(logs):
    """Test run_rag_workflow_runner_with_status with progress that has no logs"""

    # Create mock progress object with no logs
    progress_update = RagProgress(
        total_document_count=3,
        total_document_completed_count=2,
        total_document_extracted_count=3,
        total_document_chunked_count=2,
        total_document_embedded_count=2,
        logs=logs,  # No logs
    )

    # Create a simple async generator for the mock runner
    async def mock_run():
        yield progress_update

    # Create mock runner
    mock_runner = MagicMock()
    mock_runner.run.return_value = mock_run()

    # Call the function
    response = await run_rag_workflow_runner_with_status(mock_runner)

    # Read the streaming content
    content = ""
    async for chunk in response.body_iterator:
        content += str(chunk)

    # Parse the SSE content
    lines = content.strip().split("\n")
    data_lines = [line for line in lines if line.startswith("data: ")]

    # Should have 2 data events (1 progress update + 1 complete)
    assert len(data_lines) == 2

    # Check the progress data
    json_str = data_lines[0][6:]  # Remove "data: " prefix
    data = json.loads(json_str)

    assert data["total_document_count"] == 3
    assert data["total_document_completed_count"] == 2
    assert data["total_document_extracted_count"] == 3
    assert data["total_document_chunked_count"] == 2
    assert data["total_document_embedded_count"] == 2
    assert data["logs"] == []  # Should be empty list when logs is None

    # Check the final complete message
    assert data_lines[-1] == "data: complete"


@pytest.mark.asyncio
async def test_run_rag_workflow_runner_with_status_multiple_logs():
    """Test run_rag_workflow_runner_with_status with multiple log messages"""

    # Create mock progress object with multiple logs
    log_messages = [
        LogMessage(level="info", message="Starting extraction..."),
        LogMessage(level="warning", message="Some documents failed"),
        LogMessage(level="error", message="Critical error occurred"),
    ]

    progress_update = RagProgress(
        total_document_count=10,
        total_document_completed_count=8,
        total_document_extracted_count=9,
        total_document_chunked_count=8,
        total_document_embedded_count=8,
        logs=log_messages,
    )

    # Create a simple async generator for the mock runner
    async def mock_run():
        yield progress_update

    # Create mock runner
    mock_runner = MagicMock()
    mock_runner.run.return_value = mock_run()

    # Call the function
    response = await run_rag_workflow_runner_with_status(mock_runner)

    # Read the streaming content
    content = ""
    async for chunk in response.body_iterator:
        content += str(chunk)

    # Parse the SSE content
    lines = content.strip().split("\n")
    data_lines = [line for line in lines if line.startswith("data: ")]

    # Should have 2 data events (1 progress update + 1 complete)
    assert len(data_lines) == 2

    # Check the progress data
    json_str = data_lines[0][6:]  # Remove "data: " prefix
    data = json.loads(json_str)

    assert data["total_document_count"] == 10
    assert data["total_document_completed_count"] == 8
    assert len(data["logs"]) == 3

    # Check log messages
    assert data["logs"][0]["level"] == "info"
    assert data["logs"][0]["message"] == "Starting extraction..."
    assert data["logs"][1]["level"] == "warning"
    assert data["logs"][1]["message"] == "Some documents failed"
    assert data["logs"][2]["level"] == "error"
    assert data["logs"][2]["message"] == "Critical error occurred"

    # Check the final complete message
    assert data_lines[-1] == "data: complete"


@pytest.mark.asyncio
async def test_run_rag_workflow_runner_with_status_no_progress():
    """Test run_rag_workflow_runner_with_status when runner yields no progress updates"""

    # Create a simple async generator for the mock runner that yields nothing
    async def mock_run():
        if False:  # This ensures it's an async generator
            yield None

    # Create mock runner
    mock_runner = MagicMock()
    mock_runner.run.return_value = mock_run()

    # Call the function
    response = await run_rag_workflow_runner_with_status(mock_runner)

    # Read the streaming content
    content = ""
    async for chunk in response.body_iterator:
        content += str(chunk)

    # Parse the SSE content
    lines = content.strip().split("\n")
    data_lines = [line for line in lines if line.startswith("data: ")]

    # Should have only 1 data event (complete message)
    assert len(data_lines) == 1
    assert data_lines[0] == "data: complete"


# Tests for RAG search endpoint


@pytest.fixture
def mock_rag_config(
    mock_project,
    mock_extractor_config,
    mock_chunker_config,
    mock_embedding_config,
    mock_vector_store_config,
):
    rag_config = RagConfig(
        parent=mock_project,
        name="Test RAG Config",
        description="Test RAG Config description",
        extractor_config_id=mock_extractor_config.id,
        chunker_config_id=mock_chunker_config.id,
        embedding_config_id=mock_embedding_config.id,
        vector_store_config_id=mock_vector_store_config.id,
    )
    rag_config.save_to_file()
    return rag_config


@pytest.mark.asyncio
async def test_search_rag_config_fts_success(client, mock_project, mock_rag_config):
    """Test successful FTS search in RAG config"""
    search_query = "test search query"
    mock_search_results = [
        {
            "document_id": "doc_001",
            "chunk_text": "This is a test document chunk containing the search query",
            "similarity": None,
        },
        {
            "document_id": "doc_002",
            "chunk_text": "Another test chunk with relevant content",
            "similarity": None,
        },
    ]

    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
        patch(
            "kiln_server.document_api.vector_store_adapter_for_config"
        ) as mock_vector_store_adapter,
    ):
        mock_project_from_id.return_value = mock_project

        # Mock vector store adapter
        mock_adapter = AsyncMock()
        mock_adapter.search.return_value = [
            SearchResult(
                document_id=result["document_id"],
                chunk_text=result["chunk_text"],
                similarity=result["similarity"],
            )
            for result in mock_search_results
        ]
        mock_vector_store_adapter.return_value = mock_adapter

        response = client.post(
            f"/api/projects/{mock_project.id}/rag_configs/{mock_rag_config.id}/search",
            json={"query": search_query},
        )

    assert response.status_code == 200, response.text
    result = response.json()
    assert "results" in result
    assert len(result["results"]) == 2
    assert result["results"][0]["document_id"] == "doc_001"
    assert (
        result["results"][0]["chunk_text"]
        == "This is a test document chunk containing the search query"
    )
    assert result["results"][0]["similarity"] is None
    assert result["results"][1]["document_id"] == "doc_002"

    # Verify search was called with correct parameters
    mock_adapter.search.assert_called_once()
    search_call = mock_adapter.search.call_args[0][0]
    assert search_call.query_string == search_query
    assert search_call.query_embedding is None


@pytest.mark.asyncio
async def test_search_rag_config_vector_success(
    client, mock_project, mock_rag_config, mock_vector_store_config
):
    """Test successful vector search in RAG config"""
    # Update vector store config to use vector search
    mock_vector_store_config.properties.update(
        {
            "nprobes": 10,
        }
    )
    mock_vector_store_config.store_type = VectorStoreType.LANCE_DB_VECTOR
    mock_vector_store_config.save_to_file()

    search_query = "test search query"
    mock_embedding_vector = [0.1, 0.2, 0.3, 0.4, 0.5]
    mock_search_results = [
        {
            "document_id": "doc_001",
            "chunk_text": "This is a test document chunk",
            "similarity": 0.95,
        },
    ]

    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
        patch(
            "kiln_server.document_api.vector_store_adapter_for_config"
        ) as mock_vector_store_adapter,
        patch(
            "kiln_server.document_api.embedding_adapter_from_type"
        ) as mock_embedding_adapter_factory,
    ):
        mock_project_from_id.return_value = mock_project

        # Mock embedding adapter
        mock_embedding_adapter = AsyncMock()
        mock_embedding_result = MagicMock()
        mock_embedding_result.embeddings = [MagicMock(vector=mock_embedding_vector)]
        mock_embedding_adapter.generate_embeddings.return_value = mock_embedding_result
        mock_embedding_adapter_factory.return_value = mock_embedding_adapter

        # Mock vector store adapter
        mock_adapter = AsyncMock()
        mock_adapter.search.return_value = [
            SearchResult(
                document_id=result["document_id"],
                chunk_text=result["chunk_text"],
                similarity=result["similarity"],
            )
            for result in mock_search_results
        ]
        mock_vector_store_adapter.return_value = mock_adapter

        response = client.post(
            f"/api/projects/{mock_project.id}/rag_configs/{mock_rag_config.id}/search",
            json={"query": search_query},
        )

    assert response.status_code == 200, response.text
    result = response.json()
    assert "results" in result
    assert len(result["results"]) == 1
    assert result["results"][0]["document_id"] == "doc_001"
    assert result["results"][0]["similarity"] == 0.95

    # Verify embedding generation was called
    mock_embedding_adapter.generate_embeddings.assert_called_once_with([search_query])

    # Verify search was called with correct parameters
    mock_adapter.search.assert_called_once()
    search_call = mock_adapter.search.call_args[0][0]
    assert search_call.query_string is None
    assert search_call.query_embedding == mock_embedding_vector


@pytest.mark.asyncio
async def test_search_rag_config_hybrid_success(
    client, mock_project, mock_rag_config, mock_vector_store_config
):
    """Test successful hybrid search in RAG config"""
    # Update vector store config to use hybrid search
    mock_vector_store_config.properties.update(
        {
            "nprobes": 10,
        }
    )
    mock_vector_store_config.store_type = VectorStoreType.LANCE_DB_HYBRID
    mock_vector_store_config.save_to_file()

    search_query = "test search query"
    mock_embedding_vector = [0.1, 0.2, 0.3, 0.4, 0.5]
    mock_search_results = [
        {
            "document_id": "doc_001",
            "chunk_text": "This is a test document chunk",
            "similarity": 0.88,
        },
    ]

    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
        patch(
            "kiln_server.document_api.vector_store_adapter_for_config"
        ) as mock_vector_store_adapter,
        patch(
            "kiln_server.document_api.embedding_adapter_from_type"
        ) as mock_embedding_adapter_factory,
    ):
        mock_project_from_id.return_value = mock_project

        # Mock embedding adapter
        mock_embedding_adapter = AsyncMock()
        mock_embedding_result = MagicMock()
        mock_embedding_result.embeddings = [MagicMock(vector=mock_embedding_vector)]
        mock_embedding_adapter.generate_embeddings.return_value = mock_embedding_result
        mock_embedding_adapter_factory.return_value = mock_embedding_adapter

        # Mock vector store adapter
        mock_adapter = AsyncMock()
        mock_adapter.search.return_value = [
            SearchResult(
                document_id=result["document_id"],
                chunk_text=result["chunk_text"],
                similarity=result["similarity"],
            )
            for result in mock_search_results
        ]
        mock_vector_store_adapter.return_value = mock_adapter

        response = client.post(
            f"/api/projects/{mock_project.id}/rag_configs/{mock_rag_config.id}/search",
            json={"query": search_query},
        )

    assert response.status_code == 200, response.text
    result = response.json()
    assert "results" in result
    assert len(result["results"]) == 1
    assert result["results"][0]["document_id"] == "doc_001"
    assert result["results"][0]["similarity"] == 0.88

    # Verify embedding generation was called
    mock_embedding_adapter.generate_embeddings.assert_called_once_with([search_query])

    # Verify search was called with correct parameters
    mock_adapter.search.assert_called_once()
    search_call = mock_adapter.search.call_args[0][0]
    assert search_call.query_string == search_query
    assert search_call.query_embedding == mock_embedding_vector


@pytest.mark.asyncio
async def test_search_rag_config_not_found(client, mock_project):
    """Test search with non-existent RAG config"""
    with patch("kiln_server.document_api.project_from_id") as mock_project_from_id:
        mock_project_from_id.return_value = mock_project

        response = client.post(
            f"/api/projects/{mock_project.id}/rag_configs/fake_id/search",
            json={"query": "test query"},
        )

    assert response.status_code == 404, response.text
    assert "RAG config not found" in response.json()["message"]


@pytest.mark.asyncio
async def test_search_rag_config_vector_store_not_found(
    client, mock_project, mock_rag_config
):
    """Test search when vector store config is missing"""
    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
        patch(
            "kiln_ai.datamodel.vector_store.VectorStoreConfig.from_id_and_parent_path"
        ) as mock_vector_store_from_id,
    ):
        mock_project_from_id.return_value = mock_project
        mock_vector_store_from_id.return_value = None  # Simulate missing config

        response = client.post(
            f"/api/projects/{mock_project.id}/rag_configs/{mock_rag_config.id}/search",
            json={"query": "test query"},
        )

    assert response.status_code == 404, response.text
    assert "Vector store config not found" in response.json()["message"]


@pytest.mark.asyncio
async def test_search_rag_config_embedding_config_not_found(
    client, mock_project, mock_rag_config
):
    """Test search when embedding config is missing"""
    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
        patch(
            "kiln_ai.datamodel.embedding.EmbeddingConfig.from_id_and_parent_path"
        ) as mock_embedding_from_id,
    ):
        mock_project_from_id.return_value = mock_project
        mock_embedding_from_id.return_value = None  # Simulate missing config

        response = client.post(
            f"/api/projects/{mock_project.id}/rag_configs/{mock_rag_config.id}/search",
            json={"query": "test query"},
        )

    assert response.status_code == 404, response.text
    assert "Embedding config not found" in response.json()["message"]


@pytest.mark.asyncio
async def test_search_rag_config_embedding_generation_failure(
    client, mock_project, mock_rag_config, mock_vector_store_config
):
    """Test search when embedding generation fails"""
    # Update vector store config to use vector search
    mock_vector_store_config.properties.update(
        {
            "nprobes": 10,
        }
    )
    mock_vector_store_config.store_type = VectorStoreType.LANCE_DB_VECTOR
    mock_vector_store_config.save_to_file()

    search_query = "test search query"

    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
        patch(
            "kiln_server.document_api.vector_store_adapter_for_config"
        ) as mock_vector_store_adapter,
        patch(
            "kiln_server.document_api.embedding_adapter_from_type"
        ) as mock_embedding_adapter_factory,
    ):
        mock_project_from_id.return_value = mock_project

        # Mock embedding adapter to return empty embeddings
        mock_embedding_adapter = AsyncMock()
        mock_embedding_result = MagicMock()
        mock_embedding_result.embeddings = []  # Empty embeddings list
        mock_embedding_adapter.generate_embeddings.return_value = mock_embedding_result
        mock_embedding_adapter_factory.return_value = mock_embedding_adapter

        # Mock vector store adapter
        mock_adapter = AsyncMock()
        mock_vector_store_adapter.return_value = mock_adapter

        response = client.post(
            f"/api/projects/{mock_project.id}/rag_configs/{mock_rag_config.id}/search",
            json={"query": search_query},
        )

    assert response.status_code == 500, response.text
    assert (
        "Failed to generate embeddings for search query" in response.json()["message"]
    )


@pytest.mark.asyncio
async def test_search_rag_config_vector_store_search_failure(
    client, mock_project, mock_rag_config
):
    """Test search when vector store search fails"""
    search_query = "test search query"

    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
        patch(
            "kiln_server.document_api.vector_store_adapter_for_config"
        ) as mock_vector_store_adapter,
    ):
        mock_project_from_id.return_value = mock_project

        # Mock vector store adapter to raise an exception
        mock_adapter = AsyncMock()
        mock_adapter.search.side_effect = Exception("Vector store connection failed")
        mock_vector_store_adapter.return_value = mock_adapter

        response = client.post(
            f"/api/projects/{mock_project.id}/rag_configs/{mock_rag_config.id}/search",
            json={"query": search_query},
        )

    assert response.status_code == 500, response.text
    assert "Search failed: Vector store connection failed" in response.json()["message"]


@pytest.mark.asyncio
async def test_search_rag_config_empty_query(client, mock_project, mock_rag_config):
    """Test search with empty query"""
    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
        patch(
            "kiln_server.document_api.vector_store_adapter_for_config"
        ) as mock_vector_store_adapter,
    ):
        mock_project_from_id.return_value = mock_project

        # Mock vector store adapter
        mock_adapter = AsyncMock()
        mock_adapter.search.return_value = []
        mock_vector_store_adapter.return_value = mock_adapter

        response = client.post(
            f"/api/projects/{mock_project.id}/rag_configs/{mock_rag_config.id}/search",
            json={"query": ""},
        )

    # Should still work but return empty results
    assert response.status_code == 200, response.text
    result = response.json()
    assert "results" in result
    assert len(result["results"]) == 0


@pytest.mark.asyncio
async def test_search_rag_config_no_results(client, mock_project, mock_rag_config):
    """Test search that returns no results (should return empty list, not error)"""
    search_query = "nonexistent query that should return no results"

    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
        patch(
            "kiln_server.document_api.vector_store_adapter_for_config"
        ) as mock_vector_store_adapter,
    ):
        mock_project_from_id.return_value = mock_project

        # Mock vector store adapter to return empty results
        mock_adapter = AsyncMock()
        mock_adapter.search.return_value = []  # Empty results
        mock_vector_store_adapter.return_value = mock_adapter

        response = client.post(
            f"/api/projects/{mock_project.id}/rag_configs/{mock_rag_config.id}/search",
            json={"query": search_query},
        )

    # Should return 200 with empty results, not a 500 error
    assert response.status_code == 200, response.text
    result = response.json()
    assert "results" in result
    assert len(result["results"]) == 0
    assert result["results"] == []


@pytest.mark.asyncio
async def test_search_rag_config_invalid_request_body(
    client, mock_project, mock_rag_config
):
    """Test search with invalid request body"""
    with patch("kiln_server.document_api.project_from_id") as mock_project_from_id:
        mock_project_from_id.return_value = mock_project

        response = client.post(
            f"/api/projects/{mock_project.id}/rag_configs/{mock_rag_config.id}/search",
            json={"invalid_field": "test"},
        )

    assert response.status_code == 422, response.text
