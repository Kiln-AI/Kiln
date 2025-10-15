import os
import random
import time
import uuid
from dataclasses import dataclass

import pytest
from pydantic import BaseModel, Field

from kiln_ai.adapters.vector_store.lancedb_adapter import lancedb_construct_from_config
from kiln_ai.adapters.vector_store_loaders.vector_store_loader import VectorStoreLoader
from kiln_ai.datamodel.chunk import Chunk, ChunkedDocument
from kiln_ai.datamodel.datamodel_enums import KilnMimeType
from kiln_ai.datamodel.embedding import ChunkEmbeddings, Embedding
from kiln_ai.datamodel.extraction import (
    Document,
    Extraction,
    ExtractionSource,
    FileInfo,
    Kind,
)
from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.rag import RagConfig
from kiln_ai.datamodel.vector_store import VectorStoreConfig, VectorStoreType


@dataclass
class DocWithChunks:
    document: Document
    extraction: Extraction
    chunked_document: ChunkedDocument
    chunked_embeddings: ChunkEmbeddings


def lorem_ipsum(n: int) -> str:
    return " ".join(
        ["Lorem ipsum dolor sit amet, consectetur adipiscing elit." for _ in range(n)]
    )


@pytest.fixture
def mock_chunks_factory(mock_attachment_factory):
    def fn(
        project: Project,
        rag_config: RagConfig,
        num_chunks: int = 1,
        text: str | None = None,
    ) -> DocWithChunks:
        doc = Document(
            id=f"doc_{uuid.uuid4()}",
            name="Test Document",
            description="Test Document",
            original_file=FileInfo(
                filename="test.pdf",
                size=100,
                mime_type="application/pdf",
                attachment=mock_attachment_factory(KilnMimeType.PDF),
            ),
            kind=Kind.DOCUMENT,
            parent=project,
        )
        doc.save_to_file()

        extraction = Extraction(
            source=ExtractionSource.PROCESSED,
            extractor_config_id=rag_config.extractor_config_id,
            output=mock_attachment_factory(KilnMimeType.PDF),
            parent=doc,
        )
        extraction.save_to_file()

        chunks = [
            Chunk(
                content=mock_attachment_factory(
                    KilnMimeType.TXT, text=f"text-{i}: {text or lorem_ipsum(10)}"
                )
            )
            for i in range(num_chunks)
        ]
        chunked_document = ChunkedDocument(
            chunks=chunks,
            chunker_config_id=rag_config.chunker_config_id,
            parent=extraction,
        )
        chunked_document.save_to_file()
        chunked_embeddings = ChunkEmbeddings(
            embeddings=[
                Embedding(vector=[i + 0.1, i + 0.2, i + 0.3, i + 0.4, i + 0.5])
                for i in range(num_chunks)
            ],
            embedding_config_id=rag_config.embedding_config_id,
            parent=chunked_document,
        )
        chunked_embeddings.save_to_file()
        return DocWithChunks(
            document=doc,
            extraction=extraction,
            chunked_document=chunked_document,
            chunked_embeddings=chunked_embeddings,
        )

    return fn


@pytest.fixture
def mock_project(tmp_path):
    project = Project(
        name="Test Project", path=tmp_path / "test_project" / "project.kiln"
    )
    project.save_to_file()
    return project


@pytest.fixture
def rag_config_factory(mock_project):
    def fn(vector_store_config_id: str) -> RagConfig:
        rag_config = RagConfig(
            name="Test Rag Config",
            parent=mock_project,
            vector_store_config_id=vector_store_config_id,
            tool_name="test_tool",
            tool_description="test_description",
            extractor_config_id="test_extractor",
            chunker_config_id="test_chunker",
            embedding_config_id="test_embedding",
        )
        rag_config.save_to_file()
        return rag_config

    return fn


@pytest.fixture
def vector_store_config_factory(mock_project):
    def fn(vector_store_type: VectorStoreType) -> VectorStoreConfig:
        match vector_store_type:
            case VectorStoreType.LANCE_DB_FTS:
                vector_store_config = VectorStoreConfig(
                    name="Test Vector Store Config FTS",
                    parent=mock_project,
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
            case VectorStoreType.LANCE_DB_VECTOR:
                vector_store_config = VectorStoreConfig(
                    name="Test Vector Store Config KNN",
                    parent=mock_project,
                    store_type=VectorStoreType.LANCE_DB_VECTOR,
                    properties={
                        "similarity_top_k": 10,
                        "overfetch_factor": 20,
                        "vector_column_name": "vector",
                        "text_key": "text",
                        "doc_id_key": "doc_id",
                        "nprobes": 10,
                    },
                )
                vector_store_config.save_to_file()
                return vector_store_config
            case VectorStoreType.LANCE_DB_HYBRID:
                vector_store_config = VectorStoreConfig(
                    name="Test Vector Store Config Hybrid",
                    parent=mock_project,
                    store_type=VectorStoreType.LANCE_DB_HYBRID,
                    properties={
                        "similarity_top_k": 10,
                        "nprobes": 10,
                        "overfetch_factor": 20,
                        "vector_column_name": "vector",
                        "text_key": "text",
                        "doc_id_key": "doc_id",
                    },
                )
                vector_store_config.save_to_file()
                return vector_store_config
            case _:
                raise ValueError(f"Invalid vector store type: {vector_store_type}")

    return fn


class LanceDBCloudEnvVars(BaseModel):
    uri: str = Field("LANCE_DB_URI")
    api_key: str = Field("LANCE_DB_API_KEY")
    region: str = Field("LANCE_DB_REGION")


def lancedb_cloud_env_vars() -> LanceDBCloudEnvVars:
    lancedb_uri = os.getenv("LANCE_DB_URI")
    assert lancedb_uri is not None, (
        "LANCE_DB_URI is not set - test requires lancedb cloud"
    )

    lancedb_api_key = os.getenv("LANCE_DB_API_KEY")
    assert lancedb_api_key is not None, (
        "LANCE_DB_API_KEY is not set - test requires lancedb cloud"
    )

    lancedb_region = os.getenv("LANCE_DB_REGION")
    assert lancedb_region is not None, (
        "LANCE_DB_REGION is not set - test requires lancedb cloud"
    )
    return LanceDBCloudEnvVars(
        uri=lancedb_uri,
        api_key=lancedb_api_key,
        region=lancedb_region,
    )


@pytest.mark.parametrize(
    "vector_store_type",
    [
        VectorStoreType.LANCE_DB_FTS,
        VectorStoreType.LANCE_DB_VECTOR,
        VectorStoreType.LANCE_DB_HYBRID,
    ],
)
@pytest.mark.paid
async def test_lancedb_loader_insert_nodes_lancedb_cloud(
    mock_project,
    mock_chunks_factory,
    rag_config_factory,
    vector_store_type,
    vector_store_config_factory,
):
    lancedb_cloud_config = lancedb_cloud_env_vars()

    vector_store_config = vector_store_config_factory(vector_store_type)
    rag_config = rag_config_factory(vector_store_config.id)

    # init lancedb store
    now = time.time()
    table_name = f"test_lancedb_loader_insert_nodes_{vector_store_type.value}_{now}"
    lancedb_store = lancedb_construct_from_config(
        vector_store_config=vector_store_config,
        uri=lancedb_cloud_config.uri,
        api_key=lancedb_cloud_config.api_key,
        region=lancedb_cloud_config.region,
        table_name=table_name,
    )

    loader = VectorStoreLoader(
        project=mock_project,
        rag_config=rag_config,
    )

    # create nodes
    doc_count = 10
    node_count = 0
    for i in range(doc_count):
        nodes_to_add = random.randint(1, 20)
        # create mock docs, extractions, chunked documents, and chunk embeddings and persist
        mock_chunks_factory(
            mock_project,
            rag_config,
            num_chunks=nodes_to_add,
            text=f"Document {i}",
        )
        node_count += nodes_to_add

    assert node_count > 0, "No mock nodes were created"

    # insert docs
    batch_size = 100
    async for batch in loader.iter_llama_index_nodes(batch_size=batch_size):
        await lancedb_store.async_add(batch)

    # check if docs are inserted
    table = lancedb_store.table
    assert table is not None
    row_count = table.count_rows()
    assert row_count == node_count, (
        f"Expected {node_count} rows (one for each node), got {row_count} instead"
    )
