from functools import cached_property
from typing import List, TypedDict

from pydantic import BaseModel

from kiln_ai.adapters.embedding.base_embedding_adapter import BaseEmbeddingAdapter
from kiln_ai.adapters.embedding.embedding_registry import embedding_adapter_from_type
from kiln_ai.adapters.vector_store.base_vector_store_adapter import (
    BaseVectorStoreAdapter,
    SearchResult,
    VectorStoreQuery,
)
from kiln_ai.adapters.vector_store.vector_store_registry import (
    vector_store_adapter_for_config,
)
from kiln_ai.datamodel.embedding import EmbeddingConfig
from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.rag import RagConfig
from kiln_ai.datamodel.tool_id import ToolId
from kiln_ai.datamodel.vector_store import VectorStoreConfig, VectorStoreType
from kiln_ai.tools.base_tool import (
    KilnToolInterface,
    ToolCallContext,
    ToolCallDefinition,
)
from kiln_ai.utils.exhaustive_error import raise_exhaustive_enum_error


class ChunkContext(BaseModel):
    metadata: dict
    text: str

    def serialize(self) -> str:
        metadata_str = ", ".join([f"{k}: {v}" for k, v in self.metadata.items()])
        return f"[{metadata_str}]\n{self.text}\n\n"


def format_search_results(search_results: List[SearchResult]) -> str:
    results: List[ChunkContext] = []
    for search_result in search_results:
        results.append(
            ChunkContext(
                metadata={
                    "document_id": search_result.document_id,
                    "chunk_idx": search_result.chunk_idx,
                },
                text=search_result.chunk_text,
            )
        )
    return "\n=========\n".join([result.serialize() for result in results])


class RagParams(TypedDict):
    query: str


class RagTool(KilnToolInterface):
    """
    A tool that searches the vector store and returns the most relevant chunks.
    """

    def __init__(self, tool_id: str, rag_config: RagConfig):
        self._id = tool_id
        self._name = rag_config.tool_name
        self._description = rag_config.tool_description
        self._parameters_schema = {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query",
                },
            },
            "required": ["query"],
        }
        self._rag_config = rag_config
        vector_store_config = VectorStoreConfig.from_id_and_parent_path(
            str(self._rag_config.vector_store_config_id), self.project.path
        )
        if vector_store_config is None:
            raise ValueError(
                f"Vector store config not found: {self._rag_config.vector_store_config_id}"
            )
        self._vector_store_config = vector_store_config
        self._vector_store_adapter: BaseVectorStoreAdapter | None = None

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

    async def vector_store(
        self,
    ) -> BaseVectorStoreAdapter:
        if self._vector_store_adapter is None:
            self._vector_store_adapter = await vector_store_adapter_for_config(
                vector_store_config=self._vector_store_config,
                rag_config=self._rag_config,
            )
        return self._vector_store_adapter

    async def id(self) -> ToolId:
        return self._id

    async def name(self) -> str:
        return self._name

    async def description(self) -> str:
        return self._description

    async def toolcall_definition(self) -> ToolCallDefinition:
        """Return the OpenAI-compatible tool definition for this tool."""
        return {
            "type": "function",
            "function": {
                "name": await self.name(),
                "description": await self.description(),
                "parameters": self._parameters_schema,
            },
        }

    async def run(self, context: ToolCallContext | None = None, **kwargs) -> str:
        kwargs = RagParams(**kwargs)
        query = kwargs["query"]

        _, embedding_adapter = self.embedding

        vector_store_adapter = await self.vector_store()
        store_query = VectorStoreQuery(
            query_embedding=None,
            query_string=query,
        )

        match self._vector_store_config.store_type:
            case VectorStoreType.LANCE_DB_HYBRID | VectorStoreType.LANCE_DB_VECTOR:
                is_vector_query = True
            case VectorStoreType.LANCE_DB_FTS:
                is_vector_query = False
            case _:
                raise_exhaustive_enum_error(self._vector_store_config.store_type)

        if is_vector_query:
            query_embedding_result = await embedding_adapter.generate_embeddings(
                [query]
            )
            if len(query_embedding_result.embeddings) == 0:
                raise ValueError("No embeddings generated")
            store_query.query_embedding = query_embedding_result.embeddings[0].vector

        search_results = await vector_store_adapter.search(store_query)
        search_results_as_text = format_search_results(search_results)

        return search_results_as_text
