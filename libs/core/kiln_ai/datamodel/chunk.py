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


class ChunkerType(str, Enum):
    FIXED_WINDOW = "fixed_window"


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
