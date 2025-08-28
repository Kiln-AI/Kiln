from functools import cached_property
from typing import Any, Dict, List

from pydantic import BaseModel

from kiln_ai.adapters.embedding.base_embedding_adapter import BaseEmbeddingAdapter
from kiln_ai.adapters.embedding.embedding_registry import embedding_adapter_from_type
from kiln_ai.adapters.vector_store.base_vector_store_adapter import (
    BaseVectorStoreAdapter,
    SimilarityMetric,
)
from kiln_ai.adapters.vector_store.registry import vector_store_adapter_for_config
from kiln_ai.datamodel.embedding import EmbeddingConfig
from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.rag import RagConfig
from kiln_ai.datamodel.vector_store import VectorStoreConfig
from kiln_ai.tools.base_tool import KilnToolInterface
from kiln_ai.tools.tool_id import ToolId


class ChunkContext(BaseModel):
    metadata: dict
    text: str


class RagTool(KilnToolInterface):
    """
    A tool that searches the vector store and returns the most relevant chunks.
    """

    def __init__(self, tool_id: str, rag_config: RagConfig):
        self._id = tool_id
        self._name = "rag"
        self._description = (
            "Search the vector store and return the most relevant chunks"
        )
        self._parameters_schema = {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The query to search the RAG index for",
                },
            },
            "required": ["query"],
        }
        self._rag_config = rag_config

    @cached_property
    def project(self) -> Project:
        project = self._rag_config.parent_project()
        if project is None:
            raise ValueError(f"RAG config {self._rag_config.id} has no project")
        return project

    @cached_property
    def embedding(
        self,
    ) -> tuple[EmbeddingConfig, BaseEmbeddingAdapter]:
        embedding_config = EmbeddingConfig.from_id_and_parent_path(
            str(self._rag_config.embedding_config_id), self.project.path
        )
        if embedding_config is None:
            raise ValueError(
                f"Embedding config not found: {self._rag_config.embedding_config_id}"
            )
        return embedding_config, embedding_adapter_from_type(embedding_config)

    @cached_property
    async def vector_store(
        self,
    ) -> tuple[VectorStoreConfig, BaseVectorStoreAdapter]:
        vector_store_config = VectorStoreConfig.from_id_and_parent_path(
            str(self._rag_config.vector_store_config_id), self.project.path
        )
        if vector_store_config is None:
            raise ValueError(
                f"Vector store config not found: {self._rag_config.vector_store_config_id}"
            )
        return vector_store_config, await vector_store_adapter_for_config(
            vector_store_config
        )

    async def id(self) -> ToolId:
        return self._id

    async def name(self) -> str:
        return self._name

    async def description(self) -> str:
        return self._description

    async def toolcall_definition(self) -> Dict[str, Any]:
        """Return the OpenAI-compatible tool definition for this tool."""
        return {
            "type": "function",
            "function": {
                "name": await self.name(),
                "description": await self.description(),
                "parameters": self._parameters_schema,
            },
        }

    async def run(self, query: str) -> str:
        print(f"Running RAG tool with query: {query}")
        _, embedding_adapter = self.embedding

        # embed query
        query_embedding_result = await embedding_adapter.generate_embeddings([query])
        if len(query_embedding_result.embeddings) == 0:
            raise ValueError("No embeddings generated")
        query_vec = query_embedding_result.embeddings[0].vector

        # TODO: the vector store adapter should be singleton and we should rather be dealing with collection here
        vector_store_config, vector_store_adapter = await self.vector_store
        collection = await vector_store_adapter.collection(self._rag_config)
        await collection.optimize()
        knn_results = await collection.search_vector(
            vector=query_vec,
            k=10,
            distance_type=SimilarityMetric.COSINE,
        )

        results: List[ChunkContext] = []
        for knn_result in knn_results:
            results.append(
                ChunkContext(
                    metadata={
                        "document_id": knn_result.document_id,
                        "chunk_idx": knn_result.chunk_idx,
                    },
                    text=knn_result.chunk_text,
                )
            )

        result = "\n=========\n".join(
            [
                f"Document ID: {result.metadata['document_id']}\n"
                f"Chunk Index: {result.metadata['chunk_idx']}\n"
                f"Text: {result.text}\n"
                f"=========\n"
                for result in results
            ]
        )

        print(f"RAG tool result: {result}")
        return result
