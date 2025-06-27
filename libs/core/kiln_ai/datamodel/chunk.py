from enum import Enum
from typing import TYPE_CHECKING, List, Union

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
    NAME_FIELD,
    KilnAttachmentModel,
    KilnParentedModel,
)

if TYPE_CHECKING:
    from kiln_ai.datamodel.extraction import Extraction
    from kiln_ai.datamodel.project import Project

DEFAULT_CHUNK_SIZE = 256
DEFAULT_CHUNK_OVERLAP = 10


def validate_fixed_window_chunker_properties(
    properties: dict[str, str | int | float | bool],
) -> dict[str, str | int | float | bool]:
    """Validate the properties for the fixed window chunker and set defaults if needed."""
    chunk_overlap = properties.get("chunk_overlap")
    chunk_size = properties.get("chunk_size")

    # avoid a situation where user provides a chunk_overlap > DEFAULT_CHUNK_SIZE
    if chunk_overlap is not None and chunk_size is None:
        raise ValueError("Chunk size is required if chunk overlap is provided.")

    if chunk_overlap is not None:
        if not isinstance(chunk_overlap, int):
            raise ValueError("Chunk overlap must be an integer.")
        if chunk_overlap < 0:
            raise ValueError("Chunk overlap must be greater than or equal to 0.")

    if chunk_size is not None:
        if not isinstance(chunk_size, int):
            raise ValueError("Chunk size must be an integer.")
        if chunk_size < 0:
            raise ValueError("Chunk size must be greater than 0.")

    if (
        isinstance(chunk_overlap, int)
        and isinstance(chunk_size, int)
        and chunk_overlap >= chunk_size
    ):
        raise ValueError("Chunk overlap must be less than chunk size.")

    def default_if_none(value: int | None, default: int) -> int:
        return value if value is not None else default

    return {
        "chunk_overlap": default_if_none(chunk_overlap, DEFAULT_CHUNK_OVERLAP),
        "chunk_size": default_if_none(chunk_size, DEFAULT_CHUNK_SIZE),
    }


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
    attachment: KilnAttachmentModel = Field(description="The attachment of the chunk.")

    @field_serializer("attachment")
    def serialize_attachment(
        self, attachment: KilnAttachmentModel, info: SerializationInfo
    ) -> dict:
        context = info.context or {}
        context["filename_prefix"] = "chunk_attachment"
        return attachment.model_dump(mode="json", context=context)


class ChunkedDocument(KilnParentedModel):
    chunker_config_id: ID_TYPE = Field(
        description="The ID of the chunker config that was used to chunk the document.",
    )
    chunks: List[Chunk] = Field(description="The chunks of the document.")

    def parent_extraction(self) -> Union["Extraction", None]:
        if self.parent is None or self.parent.__class__.__name__ != "Extraction":
            return None
        return self.parent  # type: ignore
