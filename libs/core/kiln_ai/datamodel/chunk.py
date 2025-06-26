from enum import Enum
from typing import TYPE_CHECKING, List, Union

from pydantic import (
    BaseModel,
    Field,
    SerializationInfo,
    field_serializer,
    model_validator,
)

from kiln_ai.datamodel.basemodel import (
    ID_TYPE,
    NAME_FIELD,
    KilnAttachmentModel,
    KilnParentedModel,
)

if TYPE_CHECKING:
    from kiln_ai.datamodel.extraction import Extraction
    from kiln_ai.datamodel.project import Project


class FixedWindowChunkerProperties(BaseModel):
    chunk_size: int = Field(
        description="The size of the chunk (in tokens) to use for chunking.",
        default=256,
    )
    chunk_overlap: int = Field(
        description="The overlap of the chunk to use for chunking.",
        default=10,
    )

    @model_validator(mode="after")
    def validate_chunk_overlap(self):
        if self.chunk_overlap < 0:
            raise ValueError("Chunk overlap must be greater than or equal to 0.")
        if self.chunk_size < 0:
            raise ValueError("Chunk size must be greater than 0.")
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("Chunk overlap must be less than chunk size.")
        return self


class ChunkerType(str, Enum):
    FIXED_WINDOW = "fixed_window"


class ChunkerConfig(KilnParentedModel):
    name: str = NAME_FIELD
    description: str | None = Field(
        default=None, description="The description of the chunker config"
    )
    chunker_type: ChunkerType = Field(
        description="This is used to determine the type of chunker to use.",
    )
    properties: FixedWindowChunkerProperties = Field(
        description="Properties to be used to execute the chunker config. This is chunker_type specific and should serialize to a json dict.",
    )

    # Workaround to return typed parent without importing Project
    def parent_project(self) -> Union["Project", None]:
        if self.parent is None or self.parent.__class__.__name__ != "Project":
            return None
        return self.parent  # type: ignore


class Chunk(BaseModel):
    attachment: KilnAttachmentModel = Field(description="The attachment of the chunk.")

    @field_serializer("attachment")
    def serialize_attachment(
        self, attachment: KilnAttachmentModel, info: SerializationInfo
    ) -> dict:
        context = info.context or {}
        context["filename_prefix"] = "chunk_attachment"
        return attachment.model_dump(mode="json", context=context)


class DocumentChunked(KilnParentedModel):
    name: str = NAME_FIELD
    description: str | None = Field(
        default=None,
        description="The description of the document chunked.",
    )
    chunker_config_id: ID_TYPE = Field(
        description="The ID of the chunker config that was used to chunk the document.",
    )
    chunks: List[Chunk] = Field(description="The chunks of the document.")

    def parent_extraction(self) -> Union["Extraction", None]:
        if self.parent is None or self.parent.__class__.__name__ != "Extraction":
            return None
        return self.parent  # type: ignore
