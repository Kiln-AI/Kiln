import io
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

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
    Extraction,
    ExtractionSource,
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
    build_rag_workflow_runner,
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
            "chunker_type": ChunkerType.FIXED_WINDOW,
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
def mock_vector_store_config_fts(mock_project, tmp_path):
    vector_store_config = VectorStoreConfig(
        id="kiln:vector_store:lancedb",
        parent=mock_project,
        name="Test Vector Store FTS",
        store_type=VectorStoreType.LANCE_DB_FTS,
        properties={
            "similarity_top_k": 10,
            "overfetch_factor": 20,
            "vector_column_name": "vector",
            "text_key": "text",
            "doc_id_key": "doc_id",
            "store_type": VectorStoreType.LANCE_DB_FTS,
        },
    )
    vector_store_config.save_to_file()
    return vector_store_config


@pytest.fixture
def mock_vector_store_config_vector(mock_project, tmp_path):
    vector_store_config = VectorStoreConfig(
        id="kiln:vector_store:lancedb",
        parent=mock_project,
        name="Test Vector Store Vector",
        store_type=VectorStoreType.LANCE_DB_VECTOR,
        properties={
            "similarity_top_k": 10,
            "overfetch_factor": 20,
            "vector_column_name": "vector",
            "text_key": "text",
            "doc_id_key": "doc_id",
            "nprobes": 20,
            "store_type": VectorStoreType.LANCE_DB_VECTOR,
        },
    )
    vector_store_config.save_to_file()
    return vector_store_config


@pytest.fixture
def mock_vector_store_config_hybrid(mock_project, tmp_path):
    vector_store_config = VectorStoreConfig(
        id="kiln:vector_store:lancedb",
        parent=mock_project,
        name="Test Vector Store Hybrid",
        store_type=VectorStoreType.LANCE_DB_HYBRID,
        properties={
            "similarity_top_k": 10,
            "overfetch_factor": 20,
            "vector_column_name": "vector",
            "text_key": "text",
            "doc_id_key": "doc_id",
            "nprobes": 20,
            "store_type": VectorStoreType.LANCE_DB_HYBRID,
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
    document.save_to_file()

    with patch("kiln_server.document_api.project_from_id") as mock_project_from_id:
        mock_project_from_id.return_value = project

        response = client.post(
            f"/api/projects/{project.id}/documents/edit_tags",
            json={
                "document_ids": [document.id],
                "add_tags": ["new_tag"],
            },
        )

    assert response.status_code == 200
    assert response.json()["success"] is True

    # Verify tags were added by reloading from disk
    updated_document = Document.from_id_and_parent_path(document.id, project.path)
    assert updated_document is not None
    assert "new_tag" in updated_document.tags
    assert "existing_tag" in updated_document.tags


@pytest.mark.asyncio
async def test_edit_tags_remove_success(client, mock_document):
    project = mock_document["project"]
    document = mock_document["document"]
    document.tags = ["tag1", "tag2", "tag_to_remove"]
    document.save_to_file()

    with patch("kiln_server.document_api.project_from_id") as mock_project_from_id:
        mock_project_from_id.return_value = project

        response = client.post(
            f"/api/projects/{project.id}/documents/edit_tags",
            json={
                "document_ids": [document.id],
                "remove_tags": ["tag_to_remove"],
            },
        )

    assert response.status_code == 200
    assert response.json()["success"] is True

    # Verify tags were removed by reloading from disk
    updated_document = Document.from_id_and_parent_path(document.id, project.path)
    assert updated_document is not None
    assert "tag_to_remove" not in updated_document.tags
    assert "tag1" in updated_document.tags
    assert "tag2" in updated_document.tags


@pytest.mark.asyncio
async def test_edit_tags_document_not_found(client, mock_project):
    project = mock_project

    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
        patch(
            "kiln_ai.datamodel.extraction.Document.from_ids_and_parent_path"
        ) as mock_documents_from_ids,
    ):
        mock_project_from_id.return_value = project
        mock_documents_from_ids.return_value = {}  # Empty dict means no documents found

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
                    "chunker_type": "fixed_window",
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
                    "chunker_type": "fixed_window",
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
                    "chunker_type": "fixed_window",
                    "chunk_size": chunk_size,
                    "chunk_overlap": chunk_overlap,
                },
            },
        )

    assert response.status_code == 422, response.text
    assert "Chunk overlap must be less than chunk size" in response.json()["message"]


# test for create semantic chunker config using unified endpoint
@pytest.mark.asyncio
async def test_create_semantic_chunker_config_success(client, mock_project):
    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
    ):
        mock_project_from_id.return_value = mock_project

        embedding = EmbeddingConfig(
            parent=mock_project,
            name="emb-for-chunker",
            description=None,
            model_provider_name=ModelProviderName.openai,
            model_name=EmbeddingModelName.openai_text_embedding_3_small,
            properties={},
        )
        embedding.save_to_file()

        response = client.post(
            f"/api/projects/{mock_project.id}/create_chunker_config",
            json={
                "name": "Test Semantic Chunker Config",
                "description": "Test Semantic Chunker Config description",
                "chunker_type": "semantic",
                "properties": {
                    "chunker_type": "semantic",
                    "embedding_config_id": str(embedding.id),
                    "buffer_size": 2,
                    "breakpoint_percentile_threshold": 90,
                    "include_metadata": False,
                    "include_prev_next_rel": False,
                },
            },
        )

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["id"] is not None
    assert result["name"] == "Test Semantic Chunker Config"
    assert result["description"] == "Test Semantic Chunker Config description"
    assert result["chunker_type"] == "semantic"
    assert result["properties"]["embedding_config_id"] == str(embedding.id)
    assert result["properties"]["buffer_size"] == 2
    assert result["properties"]["breakpoint_percentile_threshold"] == 90.0
    assert result["properties"]["include_metadata"] is False
    assert result["properties"]["include_prev_next_rel"] is False


async def test_create_semantic_chunker_config_override_include_metadata_and_include_prev_next_rel(
    client, mock_project
):
    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
    ):
        mock_project_from_id.return_value = mock_project

        embedding = EmbeddingConfig(
            parent=mock_project,
            name="emb-for-chunker",
            description=None,
            model_provider_name=ModelProviderName.openai,
            model_name=EmbeddingModelName.openai_text_embedding_3_small,
            properties={},
        )
        embedding.save_to_file()

        response = client.post(
            f"/api/projects/{mock_project.id}/create_chunker_config",
            json={
                "name": "Test Semantic Chunker Config",
                "description": "Test Semantic Chunker Config description",
                "chunker_type": "semantic",
                "properties": {
                    "chunker_type": "semantic",
                    "embedding_config_id": str(embedding.id),
                    "buffer_size": 2,
                    "breakpoint_percentile_threshold": 90,
                    "include_metadata": True,
                    "include_prev_next_rel": True,
                },
            },
        )

    assert response.status_code == 200, response.text
    result = response.json()

    # we currently override these in the API layer - they are too granular to be exposed to the user in the UI
    # we could expose those in the future, if we want to allow users to override them
    assert result["properties"]["include_metadata"] is False
    assert result["properties"]["include_prev_next_rel"] is False


@pytest.mark.asyncio
async def test_create_semantic_chunker_config_minimal(client, mock_project):
    """Test creating semantic chunker config with only required fields."""
    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
    ):
        mock_project_from_id.return_value = mock_project

        embedding = EmbeddingConfig(
            parent=mock_project,
            name="emb-for-chunker-min",
            description=None,
            model_provider_name=ModelProviderName.openai,
            model_name=EmbeddingModelName.openai_text_embedding_3_small,
            properties={},
        )
        embedding.save_to_file()

        response = client.post(
            f"/api/projects/{mock_project.id}/create_chunker_config",
            json={
                "chunker_type": "semantic",
                "properties": {
                    "chunker_type": "semantic",
                    "embedding_config_id": str(embedding.id),
                    "buffer_size": 1,
                    "breakpoint_percentile_threshold": 95,
                    "include_metadata": False,
                    "include_prev_next_rel": False,
                },
            },
        )

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["id"] is not None
    assert result["chunker_type"] == "semantic"
    assert result["properties"]["embedding_config_id"] == str(embedding.id)
    assert result["properties"]["buffer_size"] == 1
    assert result["properties"]["breakpoint_percentile_threshold"] == 95
    # These are set by the endpoint
    assert result["properties"]["include_metadata"] is False
    assert result["properties"]["include_prev_next_rel"] is False


@pytest.mark.asyncio
async def test_create_semantic_chunker_config_missing_embedding_config_id(
    client, mock_project
):
    """Test creating semantic chunker config with missing embedding_config_id."""
    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
    ):
        mock_project_from_id.return_value = mock_project

        response = client.post(
            f"/api/projects/{mock_project.id}/create_chunker_config",
            json={
                "chunker_type": "semantic",
                "properties": {
                    "chunker_type": "semantic",
                    "breakpoint_percentile_threshold": 95,
                    "buffer_size": 1,
                    "include_metadata": False,
                    "include_prev_next_rel": False,
                },
            },
        )

    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_create_semantic_chunker_config_missing_buffer_size(
    client, mock_project, mock_embedding_config
):
    """Test creating semantic chunker config with missing buffer_size."""
    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
        patch(
            "kiln_ai.datamodel.embedding.EmbeddingConfig.from_id_and_parent_path"
        ) as mock_from_id,
    ):
        mock_project_from_id.return_value = mock_project
        mock_from_id.return_value = mock_embedding_config

        response = client.post(
            f"/api/projects/{mock_project.id}/create_chunker_config",
            json={
                "chunker_type": "semantic",
                "properties": {
                    "chunker_type": "semantic",
                    "breakpoint_percentile_threshold": 95,
                    "embedding_config_id": "emb-1",
                    "include_metadata": False,
                    "include_prev_next_rel": False,
                },
            },
        )

    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_create_semantic_chunker_config_missing_breakpoint_threshold(
    client, mock_project, mock_embedding_config
):
    """Test creating semantic chunker config with missing breakpoint_percentile_threshold."""
    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
        patch(
            "kiln_ai.datamodel.embedding.EmbeddingConfig.from_id_and_parent_path"
        ) as mock_from_id,
    ):
        mock_project_from_id.return_value = mock_project
        mock_from_id.return_value = mock_embedding_config

        response = client.post(
            f"/api/projects/{mock_project.id}/create_chunker_config",
            json={
                "chunker_type": "semantic",
                "properties": {
                    "chunker_type": "semantic",
                    "buffer_size": 1,
                    "embedding_config_id": "emb-1",
                    "include_metadata": False,
                    "include_prev_next_rel": False,
                },
            },
        )

    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_create_semantic_chunker_config_invalid_buffer_size(
    client, mock_project, mock_embedding_config
):
    """Test creating semantic chunker config with invalid buffer size."""
    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
        patch(
            "kiln_ai.datamodel.embedding.EmbeddingConfig.from_id_and_parent_path"
        ) as mock_from_id,
    ):
        mock_project_from_id.return_value = mock_project
        mock_from_id.return_value = mock_embedding_config

        response = client.post(
            f"/api/projects/{mock_project.id}/create_chunker_config",
            json={
                "chunker_type": "semantic",
                "properties": {
                    "chunker_type": "semantic",
                    "buffer_size": 0,  # Invalid buffer size
                    "breakpoint_percentile_threshold": 95,
                    "embedding_config_id": "emb-1",
                    "include_metadata": False,
                    "include_prev_next_rel": False,
                },
            },
        )

    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_create_semantic_chunker_config_invalid_breakpoint_threshold(
    client, mock_project, mock_embedding_config
):
    """Test creating semantic chunker config with invalid breakpoint threshold."""
    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
        patch(
            "kiln_ai.datamodel.embedding.EmbeddingConfig.from_id_and_parent_path"
        ) as mock_from_id,
    ):
        mock_project_from_id.return_value = mock_project
        mock_from_id.return_value = mock_embedding_config

        response = client.post(
            f"/api/projects/{mock_project.id}/create_chunker_config",
            json={
                "chunker_type": "semantic",
                "properties": {
                    "chunker_type": "semantic",
                    "buffer_size": 1,
                    "breakpoint_percentile_threshold": 150.0,  # Invalid threshold
                    "embedding_config_id": "emb-1",
                    "include_metadata": False,
                    "include_prev_next_rel": False,
                },
            },
        )

    assert response.status_code == 422, response.text
    assert "breakpoint_percentile_threshold" in response.json()["message"]


async def test_create_semantic_chunker_config_embedding_config_not_found(
    client, mock_project
):
    """Should return 404 if embedding_config_id does not exist."""
    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
    ):
        mock_project_from_id.return_value = mock_project

        response = client.post(
            f"/api/projects/{mock_project.id}/create_chunker_config",
            json={
                "name": "Bad Semantic Chunker Config",
                "chunker_type": "semantic",
                "properties": {
                    "chunker_type": "semantic",
                    "embedding_config_id": "does-not-exist",
                    "buffer_size": 2,
                    "breakpoint_percentile_threshold": 90,
                    "include_metadata": False,
                    "include_prev_next_rel": False,
                },
            },
        )

    assert response.status_code == 404, response.text
    assert "Embedding config does-not-exist not found" in response.text


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
    error_message = response.json()["message"]
    assert error_message
    assert (
        "Properties.Dimensions: Input should be greater than 0" in error_message
        or "Dimensions must be less than the model's dimensions" in error_message
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
async def test_create_vector_store_config_success(client, mock_project):
    with patch("kiln_server.document_api.project_from_id") as mock_project_from_id:
        mock_project_from_id.return_value = mock_project
        response = client.post(
            f"/api/projects/{mock_project.id}/create_vector_store_config",
            json={
                "name": "Test Vector Store",
                "description": "Test vector store description",
                "store_type": "lancedb_fts",
                "properties": {
                    "similarity_top_k": 10,
                },
            },
        )

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["id"] is not None
    assert result["name"] == "Test Vector Store"
    assert result["description"] == "Test vector store description"
    assert result["store_type"] == "lancedb_fts"
    assert result["properties"]["similarity_top_k"] == 10
    assert result["properties"]["overfetch_factor"] == 1
    assert result["properties"]["vector_column_name"] == "vector"
    assert result["properties"]["text_key"] == "text"
    assert result["properties"]["doc_id_key"] == "doc_id"


@pytest.mark.asyncio
async def test_create_vector_store_config_with_hybrid_type(client, mock_project):
    with patch("kiln_server.document_api.project_from_id") as mock_project_from_id:
        mock_project_from_id.return_value = mock_project
        response = client.post(
            f"/api/projects/{mock_project.id}/create_vector_store_config",
            json={
                "name": "Test Hybrid Vector Store",
                "store_type": "lancedb_hybrid",
                "properties": {
                    "similarity_top_k": 5,
                    "nprobes": 20,
                },
            },
        )

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["store_type"] == "lancedb_hybrid"
    assert result["properties"]["nprobes"] == 20

    # these are set by default
    assert result["properties"]["overfetch_factor"] == 1
    assert result["properties"]["vector_column_name"] == "vector"
    assert result["properties"]["text_key"] == "text"
    assert result["properties"]["doc_id_key"] == "doc_id"


@pytest.mark.asyncio
async def test_get_vector_store_configs(
    client, mock_project, mock_vector_store_config_fts
):
    with patch("kiln_server.document_api.project_from_id") as mock_project_from_id:
        mock_project_from_id.return_value = mock_project
        response = client.get(f"/api/projects/{mock_project.id}/vector_store_configs")

    assert response.status_code == 200, response.text
    result = response.json()
    assert len(result) == 1
    assert result[0]["name"] == "Test Vector Store FTS"


@pytest.mark.asyncio
async def test_create_rag_config_success(
    client,
    mock_project,
    mock_extractor_config,
    mock_chunker_config,
    mock_embedding_config,
    mock_vector_store_config_fts,
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
                "tool_name": "test_search_tool",
                "tool_description": "A test search tool for document retrieval",
                "extractor_config_id": mock_extractor_config.id,
                "chunker_config_id": mock_chunker_config.id,
                "embedding_config_id": mock_embedding_config.id,
                "vector_store_config_id": mock_vector_store_config_fts.id,
            },
        )

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["id"] is not None
    assert result["name"] == "Test RAG Config"
    assert result["description"] == "Test RAG Config description"
    assert result["tool_name"] == "test_search_tool"
    assert result["tool_description"] == "A test search tool for document retrieval"
    assert result["extractor_config_id"] is not None
    assert result["chunker_config_id"] is not None
    assert result["embedding_config_id"] is not None
    assert result["vector_store_config_id"] is not None


@pytest.mark.parametrize(
    "missing_config_type",
    [
        "extractor_config_id",
        "chunker_config_id",
        "embedding_config_id",
        "vector_store_config_id",
    ],
)
@pytest.mark.asyncio
async def test_create_rag_config_missing_config(
    client,
    mock_project,
    mock_extractor_config,
    mock_chunker_config,
    mock_embedding_config,
    mock_vector_store_config_fts,
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
            "tool_name": "Test Search Tool",
            "tool_description": "A test search tool for missing config testing",
            "extractor_config_id": mock_extractor_config.id,
            "chunker_config_id": mock_chunker_config.id,
            "embedding_config_id": mock_embedding_config.id,
            "vector_store_config_id": mock_vector_store_config_fts.id,
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
async def test_create_rag_config_with_tags(
    client,
    mock_project,
    mock_extractor_config,
    mock_chunker_config,
    mock_embedding_config,
    mock_vector_store_config_fts,
):
    """Test creating a RAG config with tag filtering"""
    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
    ):
        mock_project_from_id.return_value = mock_project
        response = client.post(
            f"/api/projects/{mock_project.id}/rag_configs/create_rag_config",
            json={
                "name": "Test RAG Config with Tags",
                "description": "Test RAG Config with tags description",
                "tool_name": "tagged_search_tool",
                "tool_description": "A search tool for testing with tags",
                "extractor_config_id": mock_extractor_config.id,
                "chunker_config_id": mock_chunker_config.id,
                "embedding_config_id": mock_embedding_config.id,
                "vector_store_config_id": mock_vector_store_config_fts.id,
                "tags": ["python", "ml", "backend"],
            },
        )

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["id"] is not None
    assert result["name"] == "Test RAG Config with Tags"
    assert result["description"] == "Test RAG Config with tags description"
    assert result["tags"] == ["python", "ml", "backend"]


@pytest.mark.asyncio
async def test_create_rag_config_with_empty_tags(
    client,
    mock_project,
    mock_extractor_config,
    mock_chunker_config,
    mock_embedding_config,
    mock_vector_store_config_fts,
):
    """Test creating a RAG config with empty tags list fails validation"""
    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
    ):
        mock_project_from_id.return_value = mock_project
        response = client.post(
            f"/api/projects/{mock_project.id}/rag_configs/create_rag_config",
            json={
                "name": "Test RAG Config empty tags",
                "description": "Test RAG Config description",
                "tool_name": "empty_tags_tool",
                "tool_description": "A search tool for testing empty tags validation",
                "extractor_config_id": mock_extractor_config.id,
                "chunker_config_id": mock_chunker_config.id,
                "embedding_config_id": mock_embedding_config.id,
                "vector_store_config_id": mock_vector_store_config_fts.id,
                "tags": [],  # Empty tags list should fail validation
            },
        )

    assert response.status_code == 422
    response_json = response.json()
    # The validation error format may vary, so check both possible structures
    if "detail" in response_json:
        error_detail = response_json["detail"]
        assert any(
            "Tags cannot be an empty list" in str(error) for error in error_detail
        )
    else:
        # Alternative error format
        assert "Tags cannot be an empty list" in str(response_json)


@pytest.mark.asyncio
async def test_create_rag_config_with_invalid_tags(
    client,
    mock_project,
    mock_extractor_config,
    mock_chunker_config,
    mock_embedding_config,
    mock_vector_store_config_fts,
):
    """Test creating a RAG config with invalid tags (empty strings) fails validation"""
    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
    ):
        mock_project_from_id.return_value = mock_project
        response = client.post(
            f"/api/projects/{mock_project.id}/rag_configs/create_rag_config",
            json={
                "name": "Test RAG Config invalid tags",
                "description": "Test RAG Config description",
                "tool_name": "invalid_tags_tool",
                "tool_description": "A search tool for testing invalid tags validation",
                "extractor_config_id": mock_extractor_config.id,
                "chunker_config_id": mock_chunker_config.id,
                "embedding_config_id": mock_embedding_config.id,
                "vector_store_config_id": mock_vector_store_config_fts.id,
                "tags": ["python", "", "ml"],  # Empty string in tags should fail
            },
        )

    assert response.status_code == 422
    response_json = response.json()
    assert "Tags cannot be empty" in response_json["message"]


@pytest.mark.asyncio
async def test_create_rag_config_with_null_tags(
    client,
    mock_project,
    mock_extractor_config,
    mock_chunker_config,
    mock_embedding_config,
    mock_vector_store_config_fts,
):
    """Test creating a RAG config with null tags (no filtering)"""
    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
    ):
        mock_project_from_id.return_value = mock_project
        response = client.post(
            f"/api/projects/{mock_project.id}/rag_configs/create_rag_config",
            json={
                "name": "Test RAG Config null tags",
                "description": "Test RAG Config description",
                "tool_name": "null_tags_tool",
                "tool_description": "A search tool for testing null tags",
                "extractor_config_id": mock_extractor_config.id,
                "chunker_config_id": mock_chunker_config.id,
                "embedding_config_id": mock_embedding_config.id,
                "vector_store_config_id": mock_vector_store_config_fts.id,
                "tags": None,
            },
        )

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["tags"] is None


@pytest.mark.asyncio
async def test_create_rag_config_tags_omitted(
    client,
    mock_project,
    mock_extractor_config,
    mock_chunker_config,
    mock_embedding_config,
    mock_vector_store_config_fts,
):
    """Test creating a RAG config without specifying tags field defaults to None"""
    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
    ):
        mock_project_from_id.return_value = mock_project
        response = client.post(
            f"/api/projects/{mock_project.id}/rag_configs/create_rag_config",
            json={
                "name": "Test RAG Config no tags field",
                "description": "Test RAG Config description",
                "tool_name": "no_tags_tool",
                "tool_description": "A search tool for testing omitted tags field",
                "extractor_config_id": mock_extractor_config.id,
                "chunker_config_id": mock_chunker_config.id,
                "embedding_config_id": mock_embedding_config.id,
                "vector_store_config_id": mock_vector_store_config_fts.id,
                # tags field omitted - should default to None
            },
        )

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["tags"] is None


@pytest.mark.asyncio
async def test_get_document_tags_success(client):
    """Test getting document tags from a project"""
    # Create mock documents with various tags
    doc1 = MagicMock()
    doc1.tags = ["python", "ml", "backend"]

    doc2 = MagicMock()
    doc2.tags = ["javascript", "frontend", "web"]

    doc3 = MagicMock()
    doc3.tags = ["python", "web"]  # Overlapping tags

    doc4 = MagicMock()
    doc4.tags = None  # No tags

    doc5 = MagicMock()
    doc5.tags = []  # Empty tags

    # Create mock project
    mock_project = MagicMock()
    mock_project.id = "test-project-123"
    mock_project.documents.return_value = [doc1, doc2, doc3, doc4, doc5]

    with patch("kiln_server.document_api.project_from_id") as mock_project_from_id:
        mock_project_from_id.return_value = mock_project
        response = client.get(f"/api/projects/{mock_project.id}/documents/tags")

    assert response.status_code == 200
    result = response.json()

    # Should return sorted unique tags
    expected_tags = ["backend", "frontend", "javascript", "ml", "python", "web"]
    assert result == expected_tags


@pytest.mark.asyncio
async def test_get_document_tags_empty_project(client):
    """Test getting document tags from a project with no documents"""
    # Create mock project with no documents
    mock_project = MagicMock()
    mock_project.id = "empty-project-123"
    mock_project.documents.return_value = []

    with patch("kiln_server.document_api.project_from_id") as mock_project_from_id:
        mock_project_from_id.return_value = mock_project
        response = client.get(f"/api/projects/{mock_project.id}/documents/tags")

    assert response.status_code == 200
    result = response.json()
    assert result == []


@pytest.mark.asyncio
async def test_get_document_tags_no_tags(client):
    """Test getting document tags from a project where no documents have tags"""
    doc1 = MagicMock()
    doc1.tags = None

    doc2 = MagicMock()
    doc2.tags = []

    # Create mock project
    mock_project = MagicMock()
    mock_project.id = "no-tags-project-123"
    mock_project.documents.return_value = [doc1, doc2]

    with patch("kiln_server.document_api.project_from_id") as mock_project_from_id:
        mock_project_from_id.return_value = mock_project
        response = client.get(f"/api/projects/{mock_project.id}/documents/tags")

    assert response.status_code == 200
    result = response.json()
    assert result == []


@pytest.mark.asyncio
async def test_get_document_tag_counts_success(client):
    """Test getting document tag counts from a project"""
    # Create mock documents with various tags
    doc1 = MagicMock()
    doc1.tags = ["python", "ml", "backend"]
    doc2 = MagicMock()
    doc2.tags = ["javascript", "python", "frontend", "web"]
    doc3 = MagicMock()
    doc3.tags = ["web"]  # Overlapping tags
    doc4 = MagicMock()
    doc4.tags = None  # No tags
    doc5 = MagicMock()
    doc5.tags = []  # Empty tags

    mock_project = MagicMock()
    mock_project.id = "tag-counts-project-123"
    mock_project.documents.return_value = [doc1, doc2, doc3, doc4, doc5]

    with patch("kiln_server.document_api.project_from_id") as mock_project_from_id:
        mock_project_from_id.return_value = mock_project
        response = client.get(f"/api/projects/{mock_project.id}/documents/tag_counts")

    assert response.status_code == 200
    result = response.json()
    # Should return tag counts: python(2), ml(1), backend(1), javascript(1), frontend(1), web(2)
    expected_counts = {
        "python": 2,
        "ml": 1,
        "backend": 1,
        "javascript": 1,
        "frontend": 1,
        "web": 2,
    }
    assert result == expected_counts


@pytest.mark.asyncio
async def test_get_document_tag_counts_empty_project(client):
    """Test getting document tag counts from a project with no documents"""
    mock_project = MagicMock()
    mock_project.id = "empty-project-123"
    mock_project.documents.return_value = []

    with patch("kiln_server.document_api.project_from_id") as mock_project_from_id:
        mock_project_from_id.return_value = mock_project
        response = client.get(f"/api/projects/{mock_project.id}/documents/tag_counts")

    assert response.status_code == 200
    result = response.json()
    assert result == {}


@pytest.mark.asyncio
async def test_get_document_tag_counts_no_tags(client):
    """Test getting document tag counts from a project where no documents have tags"""
    doc1 = MagicMock()
    doc1.tags = None
    doc2 = MagicMock()
    doc2.tags = []

    mock_project = MagicMock()
    mock_project.id = "no-tags-project-123"
    mock_project.documents.return_value = [doc1, doc2]

    with patch("kiln_server.document_api.project_from_id") as mock_project_from_id:
        mock_project_from_id.return_value = mock_project
        response = client.get(f"/api/projects/{mock_project.id}/documents/tag_counts")

    assert response.status_code == 200
    result = response.json()
    assert result == {}


@pytest.mark.asyncio
async def test_get_rag_configs_success(
    client,
    mock_project,
    mock_extractor_config,
    mock_chunker_config,
    mock_embedding_config,
    mock_vector_store_config_fts,
):
    # create a rag config
    rag_configs = [
        RagConfig(
            parent=mock_project,
            name="Test RAG Config 1",
            description="Test RAG Config 1 description",
            tool_name="test_search_tool_1",
            tool_description="First test search tool",
            extractor_config_id=mock_extractor_config.id,
            chunker_config_id=mock_chunker_config.id,
            embedding_config_id=mock_embedding_config.id,
            vector_store_config_id=mock_vector_store_config_fts.id,
        ),
        RagConfig(
            parent=mock_project,
            name="Test RAG Config 2",
            description="Test RAG Config 2 description",
            tool_name="test_search_tool_2",
            tool_description="Second test search tool",
            extractor_config_id=mock_extractor_config.id,
            chunker_config_id=mock_chunker_config.id,
            embedding_config_id=mock_embedding_config.id,
            vector_store_config_id=mock_vector_store_config_fts.id,
        ),
        RagConfig(
            parent=mock_project,
            name="Test RAG Config 3",
            description="Test RAG Config 3 description",
            tool_name="test_search_tool_3",
            tool_description="Third test search tool",
            extractor_config_id=mock_extractor_config.id,
            chunker_config_id=mock_chunker_config.id,
            embedding_config_id=mock_embedding_config.id,
            vector_store_config_id=mock_vector_store_config_fts.id,
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
        assert "is_archived" in response_rag_config
        assert response_rag_config["is_archived"] is False
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
        assert response_rag_config["tags"] == rag_config.tags


@pytest.mark.asyncio
async def test_get_rag_config_success(
    client,
    mock_project,
    mock_extractor_config,
    mock_chunker_config,
    mock_embedding_config,
    mock_vector_store_config_fts,
):
    rag_config = RagConfig(
        parent=mock_project,
        name="Test RAG Config",
        description="Test RAG Config description",
        tool_name="test_search_tool",
        tool_description="A test search tool for getting config",
        extractor_config_id=mock_extractor_config.id,
        chunker_config_id=mock_chunker_config.id,
        embedding_config_id=mock_embedding_config.id,
        vector_store_config_id=mock_vector_store_config_fts.id,
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
    assert result["tags"] == rag_config.tags


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
async def test_get_rag_configs_with_mixed_tags_success(
    client,
    mock_project,
    mock_extractor_config,
    mock_chunker_config,
    mock_embedding_config,
    mock_vector_store_config_fts,
):
    """Test getting multiple RAG configs with mixed tags (some with tags, some without)"""
    # Create RAG configs with different tag scenarios
    rag_configs = [
        RagConfig(
            parent=mock_project,
            name="RAG Config with Tags",
            description="Has tags",
            tool_name="test_search_tool",
            tool_description="A test search tool for document retrieval",
            extractor_config_id=mock_extractor_config.id,
            chunker_config_id=mock_chunker_config.id,
            embedding_config_id=mock_embedding_config.id,
            vector_store_config_id=mock_vector_store_config_fts.id,
            tags=["python", "ml"],
        ),
        RagConfig(
            parent=mock_project,
            name="RAG Config without Tags",
            description="No tags (None)",
            tool_name="test_search_tool",
            tool_description="A test search tool for document retrieval",
            extractor_config_id=mock_extractor_config.id,
            chunker_config_id=mock_chunker_config.id,
            embedding_config_id=mock_embedding_config.id,
            vector_store_config_id=mock_vector_store_config_fts.id,
            tags=None,
        ),
        RagConfig(
            parent=mock_project,
            name="RAG Config with Different Tags",
            description="Has different tags",
            tool_name="test_search_tool",
            tool_description="A test search tool for document retrieval",
            extractor_config_id=mock_extractor_config.id,
            chunker_config_id=mock_chunker_config.id,
            embedding_config_id=mock_embedding_config.id,
            vector_store_config_id=mock_vector_store_config_fts.id,
            tags=["frontend", "api"],
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

    # Sort both lists by id for consistent comparison
    sorted_result = sorted(result, key=lambda x: x["id"])
    sorted_rag_configs = sorted(rag_configs, key=lambda x: str(x.id))

    for response_rag_config, rag_config in zip(sorted_result, sorted_rag_configs):
        assert response_rag_config["id"] == rag_config.id
        assert response_rag_config["name"] == rag_config.name
        assert response_rag_config["description"] == rag_config.description
        assert response_rag_config["tags"] == rag_config.tags


@pytest.mark.asyncio
async def test_patch_rag_config_only_updates_is_archived(
    client,
    mock_project,
    mock_extractor_config,
    mock_chunker_config,
    mock_embedding_config,
    mock_vector_store_config_fts,
):
    rag_config = RagConfig(
        parent=mock_project,
        name="Patch Name",
        description="Patch Desc",
        tool_name="tool",
        tool_description="tdesc",
        extractor_config_id=mock_extractor_config.id,
        chunker_config_id=mock_chunker_config.id,
        embedding_config_id=mock_embedding_config.id,
        vector_store_config_id=mock_vector_store_config_fts.id,
        tags=["a"],
    )
    rag_config.save_to_file()

    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
    ):
        mock_project_from_id.return_value = mock_project
        # Only toggle archived
        response = client.patch(
            f"/api/projects/{mock_project.id}/rag_configs/{rag_config.id}",
            json={"is_archived": True},
        )

    assert response.status_code == 200
    updated = response.json()
    # is_archived updated, other fields unchanged
    assert updated["is_archived"] is True
    assert updated["name"] == "Patch Name"
    assert updated["description"] == "Patch Desc"

    # Unarchive again
    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
    ):
        mock_project_from_id.return_value = mock_project
        response = client.patch(
            f"/api/projects/{mock_project.id}/rag_configs/{rag_config.id}",
            json={"is_archived": False},
        )
    assert response.status_code == 200
    assert response.json()["is_archived"] is False
    assert updated["name"] == "Patch Name"
    assert updated["description"] == "Patch Desc"


@pytest.mark.asyncio
async def test_run_rag_config_returns_error_when_archived(
    client,
    mock_project,
    mock_extractor_config,
    mock_chunker_config,
    mock_embedding_config,
    mock_vector_store_config_fts,
):
    rag_config = RagConfig(
        parent=mock_project,
        name="Run RAG",
        description="",
        tool_name="tool",
        tool_description="tdesc",
        extractor_config_id=mock_extractor_config.id,
        chunker_config_id=mock_chunker_config.id,
        embedding_config_id=mock_embedding_config.id,
        vector_store_config_id=mock_vector_store_config_fts.id,
        tags=None,
        is_archived=True,
    )
    rag_config.save_to_file()

    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
        patch("kiln_ai.utils.shared_async_lock_manager") as mock_lock_manager,
    ):
        mock_project_from_id.return_value = mock_project
        mock_lock_manager.acquire.return_value.__aenter__ = AsyncMock()
        mock_lock_manager.acquire.return_value.__aexit__ = AsyncMock()
        response = client.get(
            f"/api/projects/{mock_project.id}/rag_configs/{rag_config.id}/run"
        )

    assert response.status_code == 422
    assert "archived" in response.json()["message"].lower()


@pytest.mark.asyncio
async def test_update_rag_config_success(
    client,
    mock_project,
    mock_extractor_config,
    mock_chunker_config,
    mock_embedding_config,
    mock_vector_store_config_fts,
):
    """Test successful update of RAG config"""
    # Create a rag config
    rag_config = RagConfig(
        parent=mock_project,
        name="Original RAG Config",
        description="Original description",
        tool_name="original_search_tool",
        tool_description="Original search tool",
        extractor_config_id=mock_extractor_config.id,
        chunker_config_id=mock_chunker_config.id,
        embedding_config_id=mock_embedding_config.id,
        vector_store_config_id=mock_vector_store_config_fts.id,
    )
    rag_config.save_to_file()

    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
        patch(
            "kiln_ai.datamodel.rag.RagConfig.from_id_and_parent_path"
        ) as mock_rag_from_id,
    ):
        mock_project_from_id.return_value = mock_project
        mock_rag_from_id.return_value = rag_config

        response = client.patch(
            f"/api/projects/{mock_project.id}/rag_configs/{rag_config.id}",
            json={
                "name": "Updated RAG Config",
                "description": "Updated description",
            },
        )

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["name"] == "Updated RAG Config"
    assert result["description"] == "Updated description"
    assert result["id"] == rag_config.id

    # Verify the config was updated
    assert rag_config.name == "Updated RAG Config"
    assert rag_config.description == "Updated description"

    # Load from disk and verify the change
    assert rag_config.path is not None
    rag_config_from_disk = RagConfig.load_from_file(rag_config.path)
    assert rag_config_from_disk.name == "Updated RAG Config"
    assert rag_config_from_disk.description == "Updated description"


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
    mock_vector_store_config_fts,
):
    # Create a rag config
    rag_config = RagConfig(
        parent=mock_project,
        name="Test RAG Config",
        description="Test RAG Config description",
        tool_name="test_search_tool",
        tool_description="A test search tool for document retrieval",
        extractor_config_id=mock_extractor_config.id,
        chunker_config_id=mock_chunker_config.id,
        embedding_config_id=mock_embedding_config.id,
        vector_store_config_id=mock_vector_store_config_fts.id,
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
    # build_rag_workflow_runner is now called inside the factory, so we don't check it directly
    # Instead check that run_rag_workflow_runner_with_status was called with a factory
    mock_run_runner.assert_called_once()
    # Verify the factory was called by checking the call args
    call_args = mock_run_runner.call_args[0]
    assert callable(call_args[0])  # First argument should be the factory function


@pytest.mark.asyncio
async def test_run_rag_config_not_found(client, mock_project):
    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
        patch(
            "kiln_server.document_api.get_rag_config_from_id"
        ) as mock_get_rag_config_from_id,
        patch(
            "kiln_server.document_api.build_rag_workflow_runner"
        ) as mock_build_runner,
        patch("kiln_ai.utils.lock.shared_async_lock_manager") as mock_lock_manager,
    ):
        mock_project_from_id.return_value = mock_project
        mock_build_runner.side_effect = HTTPException(
            status_code=404, detail="RAG config not found"
        )
        mock_lock_manager.acquire.return_value.__aenter__ = AsyncMock()
        mock_lock_manager.acquire.return_value.__aexit__ = AsyncMock()
        mock_get_rag_config_from_id.return_value = MagicMock(spec=RagConfig)
        mock_get_rag_config_from_id.return_value.is_archived = False

        response = client.get(
            f"/api/projects/{mock_project.id}/rag_configs/fake_id/run"
        )

    # Now returns 200 with streaming response containing error message
    assert response.status_code == 200
    content = response.content.decode()
    # Should contain error message in the streaming response
    assert "RAG config not found" in content or "Unexpected server error" in content


@pytest.mark.asyncio
async def test_run_rag_config_missing_configs(
    client,
    mock_project,
    mock_extractor_config,
    mock_chunker_config,
    mock_embedding_config,
    mock_vector_store_config_fts,
):
    # Create a rag config with missing configs
    rag_config = RagConfig(
        parent=mock_project,
        name="Test RAG Config",
        description="Test RAG Config description",
        tool_name="test_search_tool",
        tool_description="A test search tool for document retrieval",
        extractor_config_id=mock_extractor_config.id,
        chunker_config_id=mock_chunker_config.id,
        embedding_config_id=mock_embedding_config.id,
        vector_store_config_id=mock_vector_store_config_fts.id,
    )
    rag_config.save_to_file()

    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
        patch(
            "kiln_server.document_api.build_rag_workflow_runner"
        ) as mock_build_runner,
        patch("kiln_ai.utils.lock.shared_async_lock_manager") as mock_lock_manager,
    ):
        mock_project_from_id.return_value = mock_project
        mock_build_runner.side_effect = HTTPException(
            status_code=400, detail="RAG config is missing required configs"
        )
        mock_lock_manager.acquire.return_value.__aenter__ = AsyncMock()
        mock_lock_manager.acquire.return_value.__aexit__ = AsyncMock()

        response = client.get(
            f"/api/projects/{mock_project.id}/rag_configs/{rag_config.id}/run"
        )

    # Now returns 200 with streaming response containing error message
    assert response.status_code == 200
    content = response.content.decode()
    # Should contain error message in the streaming response
    assert "missing required configs" in content or "Unexpected server error" in content


@pytest.mark.asyncio
async def test_get_rag_config_progress_specific_configs(
    client,
    mock_project,
    mock_extractor_config,
    mock_chunker_config,
    mock_embedding_config,
    mock_vector_store_config_fts,
):
    # Create rag configs
    rag_configs = [
        RagConfig(
            parent=mock_project,
            name="Test RAG Config 1",
            description="Test RAG Config 1 description",
            tool_name="test_search_tool",
            tool_description="A test search tool for document retrieval",
            extractor_config_id=mock_extractor_config.id,
            chunker_config_id=mock_chunker_config.id,
            embedding_config_id=mock_embedding_config.id,
            vector_store_config_id=mock_vector_store_config_fts.id,
            is_archived=False,
        ),
        RagConfig(
            parent=mock_project,
            name="Test RAG Config 2",
            description="Test RAG Config 2 description",
            tool_name="test_search_tool",
            tool_description="A test search tool for document retrieval",
            extractor_config_id=mock_extractor_config.id,
            chunker_config_id=mock_chunker_config.id,
            embedding_config_id=mock_embedding_config.id,
            vector_store_config_id=mock_vector_store_config_fts.id,
            is_archived=True,  # we should keep archived configs in the progress
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
    mock_vector_store_config_fts,
):
    # Create rag configs
    rag_configs = [
        RagConfig(
            parent=mock_project,
            name="Test RAG Config 1",
            description="Test RAG Config 1 description",
            tool_name="test_search_tool",
            tool_description="A test search tool for document retrieval",
            extractor_config_id=mock_extractor_config.id,
            chunker_config_id=mock_chunker_config.id,
            embedding_config_id=mock_embedding_config.id,
            vector_store_config_id=mock_vector_store_config_fts.id,
        ),
        RagConfig(
            parent=mock_project,
            name="Test RAG Config 2",
            description="Test RAG Config 2 description",
            tool_name="test_search_tool",
            tool_description="A test search tool for document retrieval",
            extractor_config_id=mock_extractor_config.id,
            chunker_config_id=mock_chunker_config.id,
            embedding_config_id=mock_embedding_config.id,
            vector_store_config_id=mock_vector_store_config_fts.id,
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
    mock_vector_store_config_fts,
):
    # Create a valid rag config
    rag_config = RagConfig(
        parent=mock_project,
        name="Test RAG Config",
        description="Test RAG Config description",
        tool_name="test_search_tool",
        tool_description="A test search tool for document retrieval",
        extractor_config_id=mock_extractor_config.id,
        chunker_config_id=mock_chunker_config.id,
        embedding_config_id=mock_embedding_config.id,
        vector_store_config_id=mock_vector_store_config_fts.id,
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

    # Create an async factory that returns the mock runner
    async def mock_factory():
        return mock_runner

    # Call the function
    response = await run_rag_workflow_runner_with_status(mock_factory)

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

    # Create an async factory that returns the mock runner
    async def mock_factory():
        return mock_runner

    # Call the function
    response = await run_rag_workflow_runner_with_status(mock_factory)

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

    # Create an async factory that returns the mock runner
    async def mock_factory():
        return mock_runner

    # Call the function
    response = await run_rag_workflow_runner_with_status(mock_factory)

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

    # Create an async factory that returns the mock runner
    async def mock_factory():
        return mock_runner

    # Call the function
    response = await run_rag_workflow_runner_with_status(mock_factory)

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
def mock_rag_config_fts(
    mock_project,
    mock_extractor_config,
    mock_chunker_config,
    mock_embedding_config,
    mock_vector_store_config_fts,
):
    rag_config = RagConfig(
        parent=mock_project,
        name="Test RAG Config",
        description="Test RAG Config description",
        tool_name="test_search_tool",
        tool_description="A test search tool for document retrieval",
        extractor_config_id=mock_extractor_config.id,
        chunker_config_id=mock_chunker_config.id,
        embedding_config_id=mock_embedding_config.id,
        vector_store_config_id=mock_vector_store_config_fts.id,
    )
    rag_config.save_to_file()
    return rag_config


@pytest.fixture
def mock_rag_config_vector(
    mock_project,
    mock_extractor_config,
    mock_chunker_config,
    mock_embedding_config,
    mock_vector_store_config_vector,
):
    rag_config = RagConfig(
        parent=mock_project,
        name="Test RAG Config",
        description="Test RAG Config description",
        tool_name="test_search_tool",
        tool_description="A test search tool for document retrieval",
        extractor_config_id=mock_extractor_config.id,
        chunker_config_id=mock_chunker_config.id,
        embedding_config_id=mock_embedding_config.id,
        vector_store_config_id=mock_vector_store_config_vector.id,
    )
    rag_config.save_to_file()
    return rag_config


@pytest.fixture
def mock_rag_config_hybrid(
    mock_project,
    mock_extractor_config,
    mock_chunker_config,
    mock_embedding_config,
    mock_vector_store_config_hybrid,
):
    rag_config = RagConfig(
        parent=mock_project,
        name="Test RAG Config",
        description="Test RAG Config description",
        tool_name="test_search_tool",
        tool_description="A test search tool for document retrieval",
        extractor_config_id=mock_extractor_config.id,
        chunker_config_id=mock_chunker_config.id,
        embedding_config_id=mock_embedding_config.id,
        vector_store_config_id=mock_vector_store_config_hybrid.id,
    )
    rag_config.save_to_file()
    return rag_config


@pytest.mark.asyncio
async def test_search_rag_config_fts_success(client, mock_project, mock_rag_config_fts):
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
                chunk_idx=0,
                document_id=result["document_id"],
                chunk_text=result["chunk_text"],
                similarity=result["similarity"],
            )
            for result in mock_search_results
        ]
        mock_vector_store_adapter.return_value = mock_adapter

        response = client.post(
            f"/api/projects/{mock_project.id}/rag_configs/{mock_rag_config_fts.id}/search",
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
    client, mock_project, mock_rag_config_vector, mock_vector_store_config_vector
):
    """Test successful vector search in RAG config"""
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
                chunk_idx=0,
                document_id=result["document_id"],
                chunk_text=result["chunk_text"],
                similarity=result["similarity"],
            )
            for result in mock_search_results
        ]
        mock_vector_store_adapter.return_value = mock_adapter

        response = client.post(
            f"/api/projects/{mock_project.id}/rag_configs/{mock_rag_config_vector.id}/search",
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
    client, mock_project, mock_rag_config_hybrid, mock_vector_store_config_hybrid
):
    """Test successful hybrid search in RAG config"""
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
                chunk_idx=0,
                document_id=result["document_id"],
                chunk_text=result["chunk_text"],
                similarity=result["similarity"],
            )
            for result in mock_search_results
        ]
        mock_vector_store_adapter.return_value = mock_adapter

        response = client.post(
            f"/api/projects/{mock_project.id}/rag_configs/{mock_rag_config_hybrid.id}/search",
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
async def test_search_rag_config_archived(client, mock_project, mock_rag_config_fts):
    """Test search with archived RAG config"""
    with patch("kiln_server.document_api.project_from_id") as mock_project_from_id:
        mock_project_from_id.return_value = mock_project

        mock_rag_config_fts.is_archived = True
        mock_rag_config_fts.save_to_file()

        response = client.post(
            f"/api/projects/{mock_project.id}/rag_configs/{mock_rag_config_fts.id}/search",
            json={"query": "test query"},
        )

    assert response.status_code == 422, response.text
    assert "archived" in response.json()["message"]


@pytest.mark.asyncio
async def test_search_rag_config_vector_store_not_found(
    client, mock_project, mock_rag_config_fts
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
            f"/api/projects/{mock_project.id}/rag_configs/{mock_rag_config_fts.id}/search",
            json={"query": "test query"},
        )

    assert response.status_code == 404, response.text
    assert "Vector store config not found" in response.json()["message"]


@pytest.mark.asyncio
async def test_search_rag_config_embedding_config_not_found(
    client, mock_project, mock_rag_config_fts
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
            f"/api/projects/{mock_project.id}/rag_configs/{mock_rag_config_fts.id}/search",
            json={"query": "test query"},
        )

    assert response.status_code == 404, response.text
    assert "Embedding config not found" in response.json()["message"]


@pytest.mark.asyncio
async def test_search_rag_config_embedding_generation_failure(
    client, mock_project, mock_rag_config_vector, mock_vector_store_config_vector
):
    """Test search when embedding generation fails"""
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
            f"/api/projects/{mock_project.id}/rag_configs/{mock_rag_config_vector.id}/search",
            json={"query": search_query},
        )

    assert response.status_code == 500, response.text
    assert (
        "Failed to generate embeddings for search query" in response.json()["message"]
    )


@pytest.mark.asyncio
async def test_search_rag_config_vector_store_search_failure(
    client, mock_project, mock_rag_config_fts
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
            f"/api/projects/{mock_project.id}/rag_configs/{mock_rag_config_fts.id}/search",
            json={"query": search_query},
        )

    assert response.status_code == 500, response.text
    assert "Search failed: Vector store connection failed" in response.json()["message"]


@pytest.mark.asyncio
async def test_search_rag_config_empty_query(client, mock_project, mock_rag_config_fts):
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
            f"/api/projects/{mock_project.id}/rag_configs/{mock_rag_config_fts.id}/search",
            json={"query": ""},
        )

    # Should still work but return empty results
    assert response.status_code == 200, response.text
    result = response.json()
    assert "results" in result
    assert len(result["results"]) == 0


@pytest.mark.asyncio
async def test_search_rag_config_no_results(client, mock_project, mock_rag_config_fts):
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
            f"/api/projects/{mock_project.id}/rag_configs/{mock_rag_config_fts.id}/search",
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
    client, mock_project, mock_rag_config_fts
):
    """Test search with invalid request body"""
    with patch("kiln_server.document_api.project_from_id") as mock_project_from_id:
        mock_project_from_id.return_value = mock_project

        response = client.post(
            f"/api/projects/{mock_project.id}/rag_configs/{mock_rag_config_fts.id}/search",
            json={"invalid_field": "test"},
        )

    assert response.status_code == 422, response.text


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
    ):
        mock_project_from_id.return_value = project
        mock_save.return_value = None

        files = [("files", (filename, io.BytesIO(test_content), expected_content_type))]
        data = {"names": ["Test File"]}

        response = client.post(
            f"/api/projects/{project.id}/documents/bulk", files=files, data=data
        )

    assert response.status_code == 200, response.text
    result = response.json()
    assert "created_documents" in result
    assert "failed_files" in result
    assert len(result["created_documents"]) == 1
    assert len(result["failed_files"]) == 0
    doc = result["created_documents"][0]
    assert doc["name"] == "Test File"
    assert doc["kind"] == expected_kind
    assert doc["original_file"]["filename"] == filename
    assert doc["original_file"]["mime_type"] == expected_content_type
    assert doc["original_file"]["size"] == len(test_content)


@pytest.mark.asyncio
async def test_create_documents_bulk_success(client, mock_project):
    """Test successful bulk upload of multiple documents"""
    project = mock_project
    test_content_1 = b"test file content 1"
    test_content_2 = b"test file content 2"

    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
    ):
        mock_project_from_id.return_value = project

        files = [
            ("files", ("test1.txt", io.BytesIO(test_content_1), "text/plain")),
            ("files", ("test2.txt", io.BytesIO(test_content_2), "text/plain")),
        ]
        data = {"names": ["Custom Name 1", "Custom Name 2"]}

        response = client.post(
            f"/api/projects/{project.id}/documents/bulk", files=files, data=data
        )

    assert response.status_code == 200, response.text
    result = response.json()
    assert "created_documents" in result
    assert "failed_files" in result
    assert len(result["created_documents"]) == 2
    assert len(result["failed_files"]) == 0

    # Check first document
    assert result["created_documents"][0]["name"] == "Custom Name 1"
    assert result["created_documents"][0]["kind"] == "document"
    assert result["created_documents"][0]["original_file"]["filename"] == "test1.txt"
    assert result["created_documents"][0]["original_file"]["mime_type"] == "text/plain"
    assert result["created_documents"][0]["original_file"]["size"] == len(
        test_content_1
    )

    # Check second document
    assert result["created_documents"][1]["name"] == "Custom Name 2"
    assert result["created_documents"][1]["kind"] == "document"
    assert result["created_documents"][1]["original_file"]["filename"] == "test2.txt"
    assert result["created_documents"][1]["original_file"]["mime_type"] == "text/plain"
    assert result["created_documents"][1]["original_file"]["size"] == len(
        test_content_2
    )


@pytest.mark.asyncio
async def test_create_documents_bulk_without_names(client, mock_project):
    """Test bulk upload without providing custom names (should use filenames)"""
    project = mock_project
    test_content_1 = b"test file content 1"
    test_content_2 = b"test file content 2"

    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
    ):
        mock_project_from_id.return_value = project

        files = [
            ("files", ("test1.txt", io.BytesIO(test_content_1), "text/plain")),
            ("files", ("test2.txt", io.BytesIO(test_content_2), "text/plain")),
        ]

        response = client.post(
            f"/api/projects/{project.id}/documents/bulk", files=files
        )

    assert response.status_code == 200, response.text
    result = response.json()
    assert "created_documents" in result
    assert "failed_files" in result
    assert len(result["created_documents"]) == 2
    assert len(result["failed_files"]) == 0

    # Should use filenames as names (with dots converted to underscores)
    assert result["created_documents"][0]["name"] == "test1 txt"
    assert result["created_documents"][1]["name"] == "test2 txt"

    # Should have dots converted to spaces
    assert result["created_documents"][0]["friendly_name"] == "test1.txt"
    assert result["created_documents"][1]["friendly_name"] == "test2.txt"


@pytest.mark.asyncio
async def test_create_documents_bulk_mixed_file_types(
    client, mock_project, mock_file_factory
):
    """Test bulk upload with mixed valid file types"""
    project = mock_project
    test_text_content = b"test text content"
    test_image_file = mock_file_factory(MockFileFactoryMimeType.JPEG)
    test_image_content = Path(test_image_file).read_bytes()

    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
    ):
        mock_project_from_id.return_value = project

        files = [
            ("files", ("document.txt", io.BytesIO(test_text_content), "text/plain")),
            ("files", ("image.jpg", io.BytesIO(test_image_content), "image/jpeg")),
        ]

        response = client.post(
            f"/api/projects/{project.id}/documents/bulk", files=files
        )

    assert response.status_code == 200, response.text
    result = response.json()
    assert "created_documents" in result
    assert "failed_files" in result
    assert len(result["created_documents"]) == 2
    assert len(result["failed_files"]) == 0

    # Check document types
    assert result["created_documents"][0]["kind"] == "document"
    assert result["created_documents"][1]["kind"] == "image"


@pytest.mark.asyncio
async def test_create_documents_bulk_some_invalid_files(client, mock_project):
    """Test bulk upload where some files are invalid (should skip invalid, process valid)"""
    project = mock_project
    test_content_valid = b"valid test content"
    test_content_invalid = b"invalid test content"

    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
    ):
        mock_project_from_id.return_value = project

        files = [
            ("files", ("valid.txt", io.BytesIO(test_content_valid), "text/plain")),
            (
                "files",
                (
                    "invalid.xyz",
                    io.BytesIO(test_content_invalid),
                    "application/octet-stream",
                ),
            ),
            (
                "files",
                ("unsupported.csv", io.BytesIO(test_content_invalid), "text/csv"),
            ),
        ]

        response = client.post(
            f"/api/projects/{project.id}/documents/bulk", files=files
        )

    assert response.status_code == 200, response.text
    result = response.json()
    assert "created_documents" in result
    assert "failed_files" in result

    # Should only have the valid file
    assert len(result["created_documents"]) == 1
    assert len(result["failed_files"]) == 2  # Two invalid files
    assert result["created_documents"][0]["name"] == "valid txt"
    assert result["created_documents"][0]["friendly_name"] == "valid.txt"
    assert result["created_documents"][0]["kind"] == "document"


@pytest.mark.asyncio
async def test_create_documents_bulk_no_files(client, mock_project):
    """Test bulk upload with no files provided"""
    project = mock_project

    with patch("kiln_server.document_api.project_from_id") as mock_project_from_id:
        mock_project_from_id.return_value = project

        response = client.post(f"/api/projects/{project.id}/documents/bulk")

    assert response.status_code == 422, response.text
    assert "At least one file must be provided" in response.json()["message"]


@pytest.mark.asyncio
async def test_create_documents_bulk_all_invalid_files(client, mock_project):
    """Test bulk upload where all files are invalid"""
    project = mock_project
    test_content = b"test content"

    with patch("kiln_server.document_api.project_from_id") as mock_project_from_id:
        mock_project_from_id.return_value = project

        files = [
            (
                "files",
                ("invalid1.xyz", io.BytesIO(test_content), "application/octet-stream"),
            ),
            (
                "files",
                ("invalid2.abc", io.BytesIO(test_content), "application/octet-stream"),
            ),
        ]

        response = client.post(
            f"/api/projects/{project.id}/documents/bulk", files=files
        )

    assert response.status_code == 422, response.text
    result = response.json()
    assert "No files could be processed successfully" in result["message"]["error"]
    assert "failed_files" in result["message"]
    assert len(result["message"]["failed_files"]) == 2


@pytest.mark.asyncio
async def test_create_documents_bulk_mismatched_names_count(client, mock_project):
    """Test bulk upload with mismatched number of names and files"""
    project = mock_project
    test_content = b"test content"

    with patch("kiln_server.document_api.project_from_id") as mock_project_from_id:
        mock_project_from_id.return_value = project

        files = [
            ("files", ("test1.txt", io.BytesIO(test_content), "text/plain")),
            ("files", ("test2.txt", io.BytesIO(test_content), "text/plain")),
        ]
        data = {
            "names": ["Only One Name"]  # Only one name for two files
        }

        response = client.post(
            f"/api/projects/{project.id}/documents/bulk", files=files, data=data
        )

    assert response.status_code == 422, response.text
    assert "Number of names must match number of files" in response.json()["message"]


@pytest.mark.asyncio
async def test_create_documents_bulk_duplicate_filenames(client, mock_project):
    """Test bulk upload with files that have the same filename"""
    project = mock_project
    test_content_1 = b"test content 1"
    test_content_2 = b"test content 2"

    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
    ):
        mock_project_from_id.return_value = project

        files = [
            ("files", ("duplicate.txt", io.BytesIO(test_content_1), "text/plain")),
            ("files", ("duplicate.txt", io.BytesIO(test_content_2), "text/plain")),
        ]

        response = client.post(
            f"/api/projects/{project.id}/documents/bulk", files=files
        )

    assert response.status_code == 200, response.text
    result = response.json()
    assert "created_documents" in result
    assert "failed_files" in result

    # Both files should be processed (they have different content)
    assert len(result["created_documents"]) == 2
    assert len(result["failed_files"]) == 0
    assert result["created_documents"][0]["name"] == "duplicate txt"
    assert result["created_documents"][1]["name"] == "duplicate txt"
    assert result["created_documents"][0]["friendly_name"] == "duplicate.txt"
    assert result["created_documents"][1]["friendly_name"] == "duplicate.txt"


@pytest.mark.parametrize(
    "missing_sub_config_type,error_message",
    [
        ("extractor_config", "Extractor config not found"),
        ("chunker_config", "Chunker config not found"),
        ("embedding_config", "Embedding config not found"),
        ("vector_store_config", "Vector store config not found"),
    ],
)
async def test_build_rag_workflow_runner_sub_configs_not_found(
    mock_project,
    mock_extractor_config,
    mock_chunker_config,
    mock_embedding_config,
    mock_vector_store_config_fts,
    missing_sub_config_type,
    error_message,
):
    """Test build_rag_workflow_runner when sub configs are not found"""
    # Create a rag config
    rag_config = RagConfig(
        parent=mock_project,
        name="Test RAG Config",
        description="Test RAG Config description",
        tool_name="test_search_tool",
        tool_description="A test search tool for document retrieval",
        extractor_config_id=mock_extractor_config.id,
        chunker_config_id=mock_chunker_config.id,
        embedding_config_id=mock_embedding_config.id,
        vector_store_config_id=mock_vector_store_config_fts.id,
    )
    rag_config.save_to_file()

    with (
        patch(
            "kiln_ai.datamodel.rag.RagConfig.from_id_and_parent_path"
        ) as mock_rag_from_id,
        patch(
            "kiln_ai.datamodel.extraction.ExtractorConfig.from_id_and_parent_path"
        ) as mock_extractor_from_id,
        patch(
            "kiln_ai.datamodel.chunk.ChunkerConfig.from_id_and_parent_path"
        ) as mock_chunker_from_id,
        patch(
            "kiln_ai.datamodel.embedding.EmbeddingConfig.from_id_and_parent_path"
        ) as mock_embedding_from_id,
        patch(
            "kiln_ai.datamodel.vector_store.VectorStoreConfig.from_id_and_parent_path"
        ) as mock_vector_store_from_id,
    ):
        mock_rag_from_id.return_value = rag_config

        mock_extractor_from_id.return_value = (
            None
            if missing_sub_config_type == "extractor_config"
            else mock_extractor_config
        )
        mock_chunker_from_id.return_value = (
            None if missing_sub_config_type == "chunker_config" else mock_chunker_config
        )
        mock_embedding_from_id.return_value = (
            None
            if missing_sub_config_type == "embedding_config"
            else mock_embedding_config
        )
        mock_vector_store_from_id.return_value = (
            None
            if missing_sub_config_type == "vector_store_config"
            else mock_vector_store_config_fts
        )

        with pytest.raises(HTTPException) as exc_info:
            await build_rag_workflow_runner(mock_project, str(rag_config.id))

        assert exc_info.value.status_code == 404
        assert error_message in exc_info.value.detail


@pytest.mark.asyncio
async def test_build_rag_workflow_runner_success_with_progress(
    mock_project,
    mock_extractor_config,
    mock_chunker_config,
    mock_embedding_config,
    mock_vector_store_config_fts,
):
    """Test build_rag_workflow_runner success path including progress computation"""
    # Create a rag config
    rag_config = RagConfig(
        parent=mock_project,
        name="Test RAG Config",
        description="Test RAG Config description",
        tool_name="test_search_tool",
        tool_description="A test search tool for document retrieval",
        extractor_config_id=mock_extractor_config.id,
        chunker_config_id=mock_chunker_config.id,
        embedding_config_id=mock_embedding_config.id,
        vector_store_config_id=mock_vector_store_config_fts.id,
    )
    rag_config.save_to_file()

    mock_progress = RagProgress(
        total_document_count=5,
        total_document_completed_count=2,
        total_document_extracted_count=3,
        total_document_chunked_count=2,
        total_document_embedded_count=1,
    )

    with (
        patch(
            "kiln_ai.datamodel.rag.RagConfig.from_id_and_parent_path"
        ) as mock_rag_from_id,
        patch(
            "kiln_ai.datamodel.extraction.ExtractorConfig.from_id_and_parent_path"
        ) as mock_extractor_from_id,
        patch(
            "kiln_ai.datamodel.chunk.ChunkerConfig.from_id_and_parent_path"
        ) as mock_chunker_from_id,
        patch(
            "kiln_ai.datamodel.embedding.EmbeddingConfig.from_id_and_parent_path"
        ) as mock_embedding_from_id,
        patch(
            "kiln_ai.datamodel.vector_store.VectorStoreConfig.from_id_and_parent_path"
        ) as mock_vector_store_from_id,
        patch(
            "kiln_server.document_api.compute_current_progress_for_rag_config"
        ) as mock_compute_progress,
        patch("kiln_server.document_api.RagWorkflowRunner") as mock_runner_class,
    ):
        mock_rag_from_id.return_value = rag_config
        mock_extractor_from_id.return_value = mock_extractor_config
        mock_chunker_from_id.return_value = mock_chunker_config
        mock_embedding_from_id.return_value = mock_embedding_config
        mock_vector_store_from_id.return_value = mock_vector_store_config_fts
        mock_compute_progress.return_value = mock_progress

        mock_runner = MagicMock()
        mock_runner_class.return_value = mock_runner

        result = await build_rag_workflow_runner(mock_project, str(rag_config.id))

        assert result == mock_runner
        mock_compute_progress.assert_called_once_with(mock_project, rag_config)
        mock_runner_class.assert_called_once()


async def test_build_rag_workflow_runner_ollama_extractor_concurrency_is_one(
    mock_project,
    mock_chunker_config,
    mock_embedding_config,
    mock_vector_store_config_fts,
):
    """Ensure extractor concurrency is 1 when provider is ollama."""
    # Create an extractor config that uses the ollama provider
    extractor_config_ollama = ExtractorConfig(
        parent=mock_project,
        name="Ollama Extractor",
        description="Extractor using ollama",
        output_format=OutputFormat.TEXT,
        passthrough_mimetypes=[OutputFormat.TEXT],
        extractor_type=ExtractorType.LITELLM,
        model_provider_name=ModelProviderName.ollama,
        model_name="llama3",
        properties={
            "prompt_document": "prompt",
            "prompt_video": "prompt",
            "prompt_audio": "prompt",
            "prompt_image": "prompt",
        },
    )
    extractor_config_ollama.save_to_file()

    # Create a rag config referencing the ollama extractor
    rag_config = RagConfig(
        parent=mock_project,
        name="RAG with Ollama",
        description="Test RAG with ollama extractor",
        tool_name="test_search_tool",
        tool_description="A test search tool",
        extractor_config_id=extractor_config_ollama.id,
        chunker_config_id=mock_chunker_config.id,
        embedding_config_id=mock_embedding_config.id,
        vector_store_config_id=mock_vector_store_config_fts.id,
    )
    rag_config.save_to_file()

    with (
        patch(
            "kiln_ai.datamodel.rag.RagConfig.from_id_and_parent_path"
        ) as mock_rag_from_id,
        patch(
            "kiln_ai.datamodel.extraction.ExtractorConfig.from_id_and_parent_path"
        ) as mock_extractor_from_id,
        patch(
            "kiln_ai.datamodel.chunk.ChunkerConfig.from_id_and_parent_path"
        ) as mock_chunker_from_id,
        patch(
            "kiln_ai.datamodel.embedding.EmbeddingConfig.from_id_and_parent_path"
        ) as mock_embedding_from_id,
        patch(
            "kiln_ai.datamodel.vector_store.VectorStoreConfig.from_id_and_parent_path"
        ) as mock_vector_store_from_id,
        patch(
            "kiln_server.document_api.RagExtractionStepRunner.__init__",
            autospec=True,
        ) as mock_extract_runner_init,
        patch("kiln_server.document_api.RagWorkflowRunner") as mock_runner_class,
        patch(
            "kiln_server.document_api.compute_current_progress_for_rag_config",
            return_value=RagProgress(
                total_document_count=0,
                total_document_completed_count=0,
                total_document_extracted_count=0,
                total_document_chunked_count=0,
                total_document_embedded_count=0,
            ),
        ),
    ):
        mock_rag_from_id.return_value = rag_config
        mock_extractor_from_id.return_value = extractor_config_ollama
        mock_chunker_from_id.return_value = mock_chunker_config
        mock_embedding_from_id.return_value = mock_embedding_config
        mock_vector_store_from_id.return_value = mock_vector_store_config_fts

        # Ensure __init__ behaves like a normal constructor
        mock_extract_runner_init.return_value = None

        mock_runner = MagicMock()
        mock_runner_class.return_value = mock_runner

        result = await build_rag_workflow_runner(mock_project, str(rag_config.id))

        assert result == mock_runner
        # Validate that the extraction step is constructed with concurrency=1
        assert mock_extract_runner_init.call_count == 1
        # __init__ is autospecced; args: (self, project, extractor_config, ...)
        _, _args, kwargs = mock_extract_runner_init.mock_calls[0]
        assert kwargs.get("concurrency") == 1


def test_patch_document_success_name_only(client, mock_project, mock_document):
    """Test PATCH document endpoint with name only"""
    with patch("kiln_server.document_api.project_from_id") as mock_project_from_id:
        mock_project_from_id.return_value = mock_project

        response = client.patch(
            f"/api/projects/{mock_project.id}/documents/{mock_document['document'].id}",
            json={"name_override": "Updated Document Name"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["friendly_name"] == "Updated Document Name"
        assert (
            data["description"] == mock_document["document"].description
        )  # Should remain unchanged
        assert data["tags"] == mock_document["document"].tags  # Should remain unchanged


def test_patch_document_success_description_only(client, mock_project, mock_document):
    """Test PATCH document endpoint with description only"""
    with patch("kiln_server.document_api.project_from_id") as mock_project_from_id:
        mock_project_from_id.return_value = mock_project

        response = client.patch(
            f"/api/projects/{mock_project.id}/documents/{mock_document['document'].id}",
            json={"description": "Updated description"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == mock_document["document"].name  # Should remain unchanged
        assert data["description"] == "Updated description"
        assert data["tags"] == mock_document["document"].tags  # Should remain unchanged


def test_patch_document_success_tags_only(client, mock_project, mock_document):
    """Test PATCH document endpoint with tags only"""
    with patch("kiln_server.document_api.project_from_id") as mock_project_from_id:
        mock_project_from_id.return_value = mock_project

        new_tags = ["tag1", "tag2", "tag3"]
        response = client.patch(
            f"/api/projects/{mock_project.id}/documents/{mock_document['document'].id}",
            json={"tags": new_tags},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == mock_document["document"].name  # Should remain unchanged
        assert (
            data["description"] == mock_document["document"].description
        )  # Should remain unchanged
        assert data["tags"] == new_tags


def test_patch_document_success_all_fields(client, mock_project, mock_document):
    """Test PATCH document endpoint with all fields"""
    with patch("kiln_server.document_api.project_from_id") as mock_project_from_id:
        mock_project_from_id.return_value = mock_project

        new_name = "Completely New Name"
        new_description = "Completely new description"
        new_tags = ["new_tag1", "new_tag2"]

        response = client.patch(
            f"/api/projects/{mock_project.id}/documents/{mock_document['document'].id}",
            json={
                "name_override": new_name,
                "description": new_description,
                "tags": new_tags,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["friendly_name"] == new_name
        assert data["description"] == new_description
        assert data["tags"] == new_tags


def test_patch_document_not_found(client, mock_project):
    """Test PATCH document endpoint with non-existent document"""
    with patch("kiln_server.document_api.project_from_id") as mock_project_from_id:
        mock_project_from_id.return_value = mock_project

        response = client.patch(
            f"/api/projects/{mock_project.id}/documents/nonexistent_id",
            json={"name_override": "Updated Name"},
        )

        assert response.status_code == 404
        data = response.json()
        assert "Document not found" in data["message"]


def test_patch_document_no_fields_provided(client, mock_project, mock_document):
    """Test PATCH document endpoint with no fields provided"""
    with patch("kiln_server.document_api.project_from_id") as mock_project_from_id:
        mock_project_from_id.return_value = mock_project

        response = client.patch(
            f"/api/projects/{mock_project.id}/documents/{mock_document['document'].id}",
            json={},
        )

        assert response.status_code == 422
        data = response.json()
        assert "At least one field must be provided" in data["message"]


def test_patch_document_invalid_tags_empty_string(client, mock_project, mock_document):
    """Test PATCH document endpoint with empty string tag"""
    with patch("kiln_server.document_api.project_from_id") as mock_project_from_id:
        mock_project_from_id.return_value = mock_project

        response = client.patch(
            f"/api/projects/{mock_project.id}/documents/{mock_document['document'].id}",
            json={"tags": ["valid_tag", ""]},
        )

        assert response.status_code == 422
        data = response.json()
        assert "Tags cannot be empty strings" in data["message"]


def test_patch_document_name_revert_to_original_name(
    client, mock_project, mock_document
):
    """Test PATCH document endpoint with name revert to original name"""
    with patch("kiln_server.document_api.project_from_id") as mock_project_from_id:
        mock_project_from_id.return_value = mock_project

        original_name = mock_document["document"].original_file.filename

        response = client.patch(
            f"/api/projects/{mock_project.id}/documents/{mock_document['document'].id}",
            json={"name_override": "modified name"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["friendly_name"] == "modified name"

        response = client.patch(
            f"/api/projects/{mock_project.id}/documents/{mock_document['document'].id}",
            json={"name_override": ""},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["friendly_name"] == original_name


def test_patch_document_invalid_tags_with_spaces(client, mock_project, mock_document):
    """Test PATCH document endpoint with tag containing spaces"""
    with patch("kiln_server.document_api.project_from_id") as mock_project_from_id:
        mock_project_from_id.return_value = mock_project

        response = client.patch(
            f"/api/projects/{mock_project.id}/documents/{mock_document['document'].id}",
            json={"tags": ["valid_tag", "invalid tag"]},
        )

        assert response.status_code == 422
        data = response.json()
        assert "Tags cannot contain spaces" in data["message"]


def test_patch_document_invalid_name_too_long(client, mock_project, mock_document):
    """Test PATCH document endpoint with name too long"""
    with patch("kiln_server.document_api.project_from_id") as mock_project_from_id:
        mock_project_from_id.return_value = mock_project

        long_name = "x" * 121  # Exceeds 120 character limit
        response = client.patch(
            f"/api/projects/{mock_project.id}/documents/{mock_document['document'].id}",
            json={"name": long_name},
        )

        assert response.status_code == 422


def test_patch_document_invalid_name_empty(client, mock_project, mock_document):
    """Test PATCH document endpoint with empty name"""
    with patch("kiln_server.document_api.project_from_id") as mock_project_from_id:
        mock_project_from_id.return_value = mock_project

        response = client.patch(
            f"/api/projects/{mock_project.id}/documents/{mock_document['document'].id}",
            json={"name": ""},
        )

        assert response.status_code == 422


def test_patch_document_invalid_name_forbidden_chars(
    client, mock_project, mock_document
):
    """Test PATCH document endpoint with forbidden characters in name"""
    with patch("kiln_server.document_api.project_from_id") as mock_project_from_id:
        mock_project_from_id.return_value = mock_project

        response = client.patch(
            f"/api/projects/{mock_project.id}/documents/{mock_document['document'].id}",
            json={"name": "invalid/name"},
        )

        assert response.status_code == 422


def test_patch_document_partial_update_preserves_other_fields(
    client, mock_project, mock_document
):
    """Test that partial updates don't affect other fields"""
    with patch("kiln_server.document_api.project_from_id") as mock_project_from_id:
        mock_project_from_id.return_value = mock_project

        # First update just the name
        response1 = client.patch(
            f"/api/projects/{mock_project.id}/documents/{mock_document['document'].id}",
            json={"name_override": "Updated Name Only"},
        )
        assert response1.status_code == 200

        # Then update just the description
        response2 = client.patch(
            f"/api/projects/{mock_project.id}/documents/{mock_document['document'].id}",
            json={"description": "Updated Description Only"},
        )
        assert response2.status_code == 200

        data = response2.json()
        assert (
            data["friendly_name"] == "Updated Name Only"
        )  # Should be preserved from first update
        assert data["description"] == "Updated Description Only"  # Should be updated
        assert data["tags"] == mock_document["document"].tags  # Should remain original


@pytest.mark.parametrize(
    "invalid_data",
    [
        # Missing tool_name
        (
            {
                "name": "Missing Tool Name",
                "tool_description": "Has description but no name",
                "extractor_config_id": "test_extractor",
                "chunker_config_id": "test_chunker",
                "embedding_config_id": "test_embedding",
                "vector_store_config_id": "test_vector_store",
            },
        ),
        # Missing tool_description
        (
            {
                "name": "Missing Tool Description",
                "tool_name": "Has name but no description",
                "extractor_config_id": "test_extractor",
                "chunker_config_id": "test_chunker",
                "embedding_config_id": "test_embedding",
                "vector_store_config_id": "test_vector_store",
            },
        ),
        # Both missing
        (
            {
                "name": "Missing Both Tool Fields",
                "extractor_config_id": "test_extractor",
                "chunker_config_id": "test_chunker",
                "embedding_config_id": "test_embedding",
                "vector_store_config_id": "test_vector_store",
            },
        ),
        # Empty tool_name
        (
            {
                "name": "Empty Tool Name",
                "tool_name": "",
                "tool_description": "Has description but no name",
            },
        ),
        # Empty tool_description
        (
            {
                "name": "Empty Tool Description",
                "tool_name": "Has name but no description",
                "tool_description": "",
            },
        ),
    ],
)
@pytest.mark.asyncio
async def test_create_rag_config_invalid_tool_fields(
    client,
    mock_project,
    invalid_data,
):
    """Test that creating RAG config with invalid tool fields returns appropriate errors."""
    with patch("kiln_server.document_api.project_from_id") as mock_project_from_id:
        mock_project_from_id.return_value = mock_project
        response = client.post(
            f"/api/projects/{mock_project.id}/rag_configs/create_rag_config",
            json=invalid_data,
        )

    assert response.status_code == 422
    error_detail = response.json()
    assert "error_messages" in error_detail


@pytest.mark.parametrize(
    "tags",
    [
        [],
        ["tag1"],
        ["tag1", "tag2"],
        ["tag1", "tag2", "tag3"],
    ],
)
async def test_create_documents_bulk_with_tags_success(client, mock_project, tags):
    """Test successful bulk upload with various tag combinations"""
    project = mock_project
    test_content_1 = b"test file content 1"
    test_content_2 = b"test file content 2"

    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
    ):
        mock_project_from_id.return_value = project

        files = [
            ("files", ("test1.txt", io.BytesIO(test_content_1), "text/plain")),
            ("files", ("test2.txt", io.BytesIO(test_content_2), "text/plain")),
        ]
        data = {"names": ["Custom Name 1", "Custom Name 2"]}

        # Add tags to the data
        for tag in tags:
            data.setdefault("tags", []).append(tag)

        response = client.post(
            f"/api/projects/{project.id}/documents/bulk", files=files, data=data
        )

    assert response.status_code == 200, response.text
    result = response.json()
    assert "created_documents" in result
    assert "failed_files" in result
    assert len(result["created_documents"]) == 2
    assert len(result["failed_files"]) == 0

    # Check that both documents have all the tags
    for doc in result["created_documents"]:
        assert "tags" in doc
        assert doc["tags"] == tags
        assert len(doc["tags"]) == len(tags)
        assert sorted(tags) == sorted(doc["tags"])


@pytest.mark.parametrize(
    "invalid_tags",
    [
        ["tag with spaces"],
        ["tag with spaces", "valid_tag"],
        ["", "valid_tag"],
        ["   ", "valid_tag"],
    ],
)
async def test_create_documents_bulk_with_invalid_tags_failure(
    client, mock_project, invalid_tags
):
    """Test bulk upload failure due to invalid tags (spaces, empty strings)"""
    project = mock_project
    test_content = b"test file content"

    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
    ):
        mock_project_from_id.return_value = project

        files = [
            ("files", ("test.txt", io.BytesIO(test_content), "text/plain")),
        ]
        data = {"names": ["Custom Name"]}

        # Add invalid tags to the data
        for tag in invalid_tags:
            data.setdefault("tags", []).append(tag)

        response = client.post(
            f"/api/projects/{project.id}/documents/bulk", files=files, data=data
        )

    # Should return 422 for invalid tags
    assert response.status_code == 422, response.text
    result = response.json()
    assert "message" in result
    assert "failed_files" in result["message"]
    assert len(result["message"]["failed_files"]) == 1
    assert (
        "Tags cannot contain spaces" in result["message"]["failed_files"][0]
        or "Tags cannot be empty strings" in result["message"]["failed_files"][0]
    )


@pytest.mark.asyncio
async def test_delete_extraction_extractor_config_not_found(
    client, mock_project, mock_document
):
    with patch("kiln_server.document_api.project_from_id") as mock_project_from_id:
        mock_project_from_id.return_value = mock_project

        document = mock_document["document"]
        extraction = Extraction(
            parent=document,
            source=ExtractionSource.PROCESSED,
            extractor_config_id="nonexistent-id",
            output=KilnAttachmentModel.from_data("hello", "text/plain"),
        )
        extraction.save_to_file()

        response = client.delete(
            f"/api/projects/{mock_project.id}/documents/{document.id}/extractions/{extraction.id}",
        )

    assert response.status_code == 404


async def test_delete_extraction_success(
    client, mock_project, mock_document, mock_extractor_config
):
    """Test DELETE extraction endpoint success"""
    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
        patch(
            "kiln_server.document_api.extractor_adapter_from_type"
        ) as mock_extractor_factory,
    ):
        mock_project_from_id.return_value = mock_project

        mock_extractor = MagicMock()
        mock_extractor.clear_cache_for_file_path = AsyncMock()
        mock_extractor_factory.return_value = mock_extractor

        # Create an extraction on disk so the DELETE endpoint can find it
        document = mock_document["document"]
        extraction = Extraction(
            parent=document,
            source=ExtractionSource.PROCESSED,
            extractor_config_id=mock_extractor_config.id,  # type: ignore[arg-type]
            output=KilnAttachmentModel.from_data("hello", "text/plain"),
        )
        extraction.save_to_file()

        response = client.delete(
            f"/api/projects/{mock_project.id}/documents/{document.id}/extractions/{extraction.id}",
        )

        assert response.status_code == 200

        # Assert cache clear called with resolved attachment path
        document = mock_document["document"]
        expected_path = document.original_file.attachment.resolve_path(
            document.path.parent
        )
        mock_extractor.clear_cache_for_file_path.assert_awaited_once_with(expected_path)


async def test_delete_extraction_failed_to_clear_cache(
    client, mock_project, mock_document, mock_extractor_config
):
    """Deletion of extraction should not fail if failed to clear cache"""
    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
        patch(
            "kiln_server.document_api.extractor_adapter_from_type"
        ) as mock_extractor_factory,
        patch("kiln_server.document_api.logger") as mock_logger,
    ):
        mock_project_from_id.return_value = mock_project

        mock_extractor = MagicMock()
        mock_extractor.clear_cache_for_file_path = AsyncMock(
            side_effect=Exception("Deleting cache for file path failed"),
        )
        mock_extractor_factory.return_value = mock_extractor

        # Create an extraction on disk so the DELETE endpoint can find it
        document = mock_document["document"]
        extraction = Extraction(
            parent=document,
            source=ExtractionSource.PROCESSED,
            extractor_config_id=mock_extractor_config.id,  # type: ignore[arg-type]
            output=KilnAttachmentModel.from_data("hello", "text/plain"),
        )
        extraction.save_to_file()

        response = client.delete(
            f"/api/projects/{mock_project.id}/documents/{document.id}/extractions/{extraction.id}",
        )

        assert response.status_code == 200

        mock_logger.warning.assert_called_once()
        warning_args, _ = mock_logger.warning.call_args
        assert (
            warning_args[0]
            == "Failed to clear extractor cache for document %s (extraction %s): %s"
        )


async def test_get_embedding_config_not_found(client, mock_project):
    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
        patch(
            "kiln_ai.datamodel.embedding.EmbeddingConfig.from_id_and_parent_path"
        ) as mock_from_id,
    ):
        mock_project_from_id.return_value = mock_project
        mock_from_id.return_value = None

        response = client.get(
            f"/api/projects/{mock_project.id}/embedding_configs/not-found",
        )

    assert response.status_code == 404
    error_detail = response.json()
    assert "message" in error_detail
    assert "Embedding config not-found not found" in error_detail["message"]


async def test_get_embedding_config_success(
    client, mock_project, mock_embedding_config
):
    with (
        patch("kiln_server.document_api.project_from_id") as mock_project_from_id,
        patch(
            "kiln_ai.datamodel.embedding.EmbeddingConfig.from_id_and_parent_path"
        ) as mock_from_id,
    ):
        mock_project_from_id.return_value = mock_project
        mock_from_id.return_value = mock_embedding_config
        response = client.get(
            f"/api/projects/{mock_project.id}/embedding_configs/{mock_embedding_config.id}",
        )
    assert response.status_code == 200
    result = response.json()
    assert result["id"] == mock_embedding_config.id
    assert result["name"] == mock_embedding_config.name
    assert result["description"] == mock_embedding_config.description
    assert result["model_provider_name"] == mock_embedding_config.model_provider_name
    assert result["model_name"] == mock_embedding_config.model_name
    assert result["properties"] == mock_embedding_config.properties
