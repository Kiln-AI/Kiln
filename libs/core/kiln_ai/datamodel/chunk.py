import logging
from enum import Enum
from typing import TYPE_CHECKING, List, Union

import anyio
from pydantic import (
    BaseModel,
    Field,
    SerializationInfo,
    ValidationInfo,
    field_serializer,
    field_validator,
)

from kiln_ai.datamodel.basemodel import (
    ID_TYPE,
    FilenameString,
    KilnAttachmentModel,
    KilnParentedModel,
    KilnParentModel,
)
from kiln_ai.datamodel.embedding import ChunkEmbeddings

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from kiln_ai.datamodel.extraction import Extraction
    from kiln_ai.datamodel.project import Project


def validate_fixed_window_chunker_properties(
    properties: dict[str, str | int | float | bool],
) -> dict[str, str | int | float | bool]:
    """Validate the properties for the fixed window chunker and set defaults if needed."""
    chunk_overlap = properties.get("chunk_overlap")
    if chunk_overlap is None:
        raise ValueError("Chunk overlap is required.")

    chunk_size = properties.get("chunk_size")
    if chunk_size is None:
        raise ValueError("Chunk size is required.")

    if not isinstance(chunk_overlap, int):
        raise ValueError("Chunk overlap must be an integer.")
    if chunk_overlap < 0:
        raise ValueError("Chunk overlap must be greater than or equal to 0.")

    if not isinstance(chunk_size, int):
        raise ValueError("Chunk size must be an integer.")
    if chunk_size <= 0:
        raise ValueError("Chunk size must be greater than 0.")

    if chunk_overlap >= chunk_size:
        raise ValueError("Chunk overlap must be less than chunk size.")

    return properties


def validate_semantic_chunker_properties(
    properties: dict[str, str | int | float | bool],
) -> dict[str, str | int | float | bool]:
    """Validate the properties for the semantic chunker."""
    # Required properties
    embedding_config_id = properties.get("embedding_config_id")
    if embedding_config_id is None:
        raise ValueError("embedding_config_id is required for semantic chunker.")
    if not isinstance(embedding_config_id, str):
        raise ValueError("embedding_config_id must be a string.")

    # Optional properties - validate if present
    buffer_size = properties.get("buffer_size")
    if buffer_size is not None:
        if not isinstance(buffer_size, int):
            raise ValueError("buffer_size must be an integer.")
        if buffer_size < 1:
            raise ValueError("buffer_size must be greater than or equal to 1.")

    breakpoint_percentile_threshold = properties.get("breakpoint_percentile_threshold")
    if breakpoint_percentile_threshold is not None:
        if not isinstance(breakpoint_percentile_threshold, (int, float)):
            raise ValueError("breakpoint_percentile_threshold must be a number.")
        if not (0 <= breakpoint_percentile_threshold <= 100):
            raise ValueError(
                "breakpoint_percentile_threshold must be between 0 and 100."
            )

    include_metadata = properties.get("include_metadata")
    if include_metadata is not None:
        if not isinstance(include_metadata, bool):
            raise ValueError("include_metadata must be a boolean.")

    include_prev_next_rel = properties.get("include_prev_next_rel")
    if include_prev_next_rel is not None:
        if not isinstance(include_prev_next_rel, bool):
            raise ValueError("include_prev_next_rel must be a boolean.")

    return properties


class ChunkerType(str, Enum):
    FIXED_WINDOW = "fixed_window"
    SEMANTIC = "semantic"


class ChunkerConfig(KilnParentedModel):
    name: FilenameString = Field(
        description="A name to identify the chunker config.",
    )
    description: str | None = Field(
        default=None, description="The description of the chunker config"
    )
    chunker_type: ChunkerType = Field(
        description="This is used to determine the type of chunker to use.",
    )
    properties: dict[str, str | int | float | bool] = Field(
        description="Properties to be used to execute the chunker config. This is chunker_type specific and should serialize to a json dict.",
    )

    # Workaround to return typed parent without importing Project
    def parent_project(self) -> Union["Project", None]:
        if self.parent is None or self.parent.__class__.__name__ != "Project":
            return None
        return self.parent  # type: ignore

    @field_validator("properties")
    @classmethod
    def validate_properties(
        cls, properties: dict[str, str | int | float | bool], info: ValidationInfo
    ) -> dict[str, str | int | float | bool]:
        if info.data.get("chunker_type") == ChunkerType.FIXED_WINDOW:
            # do not trigger revalidation of properties
            return validate_fixed_window_chunker_properties(properties)
        elif info.data.get("chunker_type") == ChunkerType.SEMANTIC:
            # do not trigger revalidation of properties
            return validate_semantic_chunker_properties(properties)
        return properties

    def chunk_size(self) -> int | None:
        if self.properties.get("chunk_size") is None:
            return None
        if not isinstance(self.properties["chunk_size"], int):
            raise ValueError("Chunk size must be an integer.")
        return self.properties["chunk_size"]

    def chunk_overlap(self) -> int | None:
        if self.properties.get("chunk_overlap") is None:
            return None
        if not isinstance(self.properties["chunk_overlap"], int):
            raise ValueError("Chunk overlap must be an integer.")
        return self.properties["chunk_overlap"]

    def embedding_config_id(self) -> str | None:
        if self.properties.get("embedding_config_id") is None:
            return None
        if not isinstance(self.properties["embedding_config_id"], str):
            raise ValueError("embedding_config_id must be a string.")
        return self.properties["embedding_config_id"]

    def buffer_size(self) -> int | None:
        if self.properties.get("buffer_size") is None:
            return None
        if not isinstance(self.properties["buffer_size"], int):
            raise ValueError("Buffer size must be an integer.")
        return self.properties["buffer_size"]

    def breakpoint_percentile_threshold(self) -> int | None:
        if self.properties.get("breakpoint_percentile_threshold") is None:
            return None
        if not isinstance(self.properties["breakpoint_percentile_threshold"], int):
            raise ValueError("Breakpoint percentile threshold must be an integer.")
        if (
            self.properties["breakpoint_percentile_threshold"] < 0
            or self.properties["breakpoint_percentile_threshold"] > 100
        ):
            raise ValueError(
                "Breakpoint percentile threshold must be between 0 and 100."
            )
        return int(self.properties["breakpoint_percentile_threshold"])

    def include_metadata(self) -> bool | None:
        if self.properties.get("include_metadata") is None:
            return None
        if not isinstance(self.properties["include_metadata"], bool):
            raise ValueError("Include metadata must be a boolean.")
        return self.properties["include_metadata"]

    def include_prev_next_rel(self) -> bool | None:
        if self.properties.get("include_prev_next_rel") is None:
            return None
        if not isinstance(self.properties["include_prev_next_rel"], bool):
            raise ValueError("Include prev next rel must be a boolean.")
        return self.properties["include_prev_next_rel"]


class Chunk(BaseModel):
    content: KilnAttachmentModel = Field(
        description="The content of the chunk, stored as an attachment."
    )

    @field_serializer("content")
    def serialize_content(
        self, content: KilnAttachmentModel, info: SerializationInfo
    ) -> dict:
        context = info.context or {}
        context["filename_prefix"] = "content"
        return content.model_dump(mode="json", context=context)


class ChunkedDocument(
    KilnParentedModel, KilnParentModel, parent_of={"chunk_embeddings": ChunkEmbeddings}
):
    chunker_config_id: ID_TYPE = Field(
        description="The ID of the chunker config used to chunk the document.",
    )
    chunks: List[Chunk] = Field(description="The chunks of the document.")

    def parent_extraction(self) -> Union["Extraction", None]:
        if self.parent is None or self.parent.__class__.__name__ != "Extraction":
            return None
        return self.parent  # type: ignore

    def chunk_embeddings(self, readonly: bool = False) -> list[ChunkEmbeddings]:
        return super().chunk_embeddings(readonly=readonly)  # type: ignore

    async def load_chunks_text(self) -> list[str]:
        """Utility to return a list of text for each chunk, loaded from each chunk's content attachment."""
        if not self.path:
            raise ValueError(
                "Failed to resolve the path of chunk content attachment because the chunk does not have a path."
            )

        chunks_text: list[str] = []
        for chunk in self.chunks:
            full_path = chunk.content.resolve_path(self.path.parent)

            try:
                chunks_text.append(
                    await anyio.Path(full_path).read_text(encoding="utf-8")
                )
            except Exception as e:
                raise ValueError(
                    f"Failed to read chunk content for {full_path}: {e}"
                ) from e

        return chunks_text
