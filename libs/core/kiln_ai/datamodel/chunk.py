import logging
from enum import Enum
from typing import TYPE_CHECKING, Annotated, List, Union

import anyio
from pydantic import (
    AfterValidator,
    BaseModel,
    Field,
    NonNegativeInt,
    PositiveInt,
    SerializationInfo,
    ValidationInfo,
    field_serializer,
    model_validator,
)
from typing_extensions import Literal, TypedDict

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


class ChunkerType(str, Enum):
    FIXED_WINDOW = "fixed_window"
    SEMANTIC = "semantic"


class SemanticChunkerProperties(TypedDict, total=True):
    chunker_type: Literal[ChunkerType.SEMANTIC]
    embedding_config_id: str
    buffer_size: PositiveInt
    breakpoint_percentile_threshold: NonNegativeInt
    include_metadata: bool
    include_prev_next_rel: bool


class FixedWindowChunkerProperties(TypedDict, total=True):
    chunker_type: Literal[ChunkerType.FIXED_WINDOW]
    chunk_overlap: NonNegativeInt
    chunk_size: PositiveInt


def validate_fixed_window_chunker_properties(
    properties: FixedWindowChunkerProperties,
) -> FixedWindowChunkerProperties:
    """Validate the properties for the fixed window chunker and set defaults if needed."""
    # the typed dict only validates the shape and types, but not the logic, so we validate here
    if properties["chunk_overlap"] >= properties["chunk_size"]:
        raise ValueError("Chunk overlap must be less than chunk size.")

    return properties


def validate_semantic_chunker_properties(
    properties: SemanticChunkerProperties,
) -> SemanticChunkerProperties:
    """Validate the properties for the semantic chunker."""
    buffer_size = properties["buffer_size"]
    if buffer_size < 1:
        raise ValueError("buffer_size must be greater than or equal to 1.")

    breakpoint_percentile_threshold = properties["breakpoint_percentile_threshold"]
    if not (0 <= breakpoint_percentile_threshold <= 100):
        raise ValueError("breakpoint_percentile_threshold must be between 0 and 100.")

    return properties


SemanticChunkerPropertiesValidator = Annotated[
    SemanticChunkerProperties,
    AfterValidator(lambda v: validate_semantic_chunker_properties(v)),
]

FixedWindowChunkerPropertiesValidator = Annotated[
    FixedWindowChunkerProperties,
    AfterValidator(lambda v: validate_fixed_window_chunker_properties(v)),
]


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
    properties: (
        SemanticChunkerPropertiesValidator | FixedWindowChunkerPropertiesValidator
    ) = Field(
        description="Properties to be used to execute the chunker config. This is chunker_type specific and should serialize to a json dict.",
        discriminator="chunker_type",
    )

    # Workaround to return typed parent without importing Project
    def parent_project(self) -> Union["Project", None]:
        if self.parent is None or self.parent.__class__.__name__ != "Project":
            return None
        return self.parent  # type: ignore

    @model_validator(mode="before")
    def upgrade_missing_discriminator_properties(
        cls, data: dict, info: ValidationInfo
    ) -> dict:
        if not info.context or not info.context.get("loading_from_file", False):
            # Not loading from file, so no need to upgrade
            return data

        if not isinstance(data, dict):
            return data

        # backward compatibility:
        # - we originally did not have the chunker_type in the properties, so we need to add it here
        # - we started wanted to have chunker_type in the properties to use pydantic's discriminated union feature
        properties = data.get("properties", {})
        if "chunker_type" not in properties:
            # the chunker_type on the parent model is always there, we just need to add it to the properties
            properties["chunker_type"] = data["chunker_type"]
            data["properties"] = properties
        return data

    @model_validator(mode="after")
    def ensure_chunker_type_matches_properties(self):
        # sanity check to ensure the chunker_type matches the properties chunker_type
        if self.chunker_type != self.properties["chunker_type"]:
            raise ValueError(
                f"Chunker type mismatch: {self.chunker_type} != {self.properties['chunker_type']}. This is a bug, please report it."
            )
        return self

    # expose the typed properties based on the chunker_type
    @property
    def semantic_properties(self) -> SemanticChunkerProperties:
        if self.properties["chunker_type"] != ChunkerType.SEMANTIC:
            raise ValueError(
                "Semantic properties are only available for semantic chunker."
            )
        # TypedDict cannot be checked at runtime, so we need to ignore the type check
        # or cast (but it is currently banned in our linting rules). Better solution
        # would be discriminated union, but that requires the discriminator to be part
        # of the properties (not outside on the parent model).
        return self.properties

    @property
    def fixed_window_properties(self) -> FixedWindowChunkerProperties:
        if self.properties["chunker_type"] != ChunkerType.FIXED_WINDOW:
            raise ValueError(
                "Fixed window properties are only available for fixed window chunker."
            )
        # TypedDict cannot be checked at runtime, so we need to ignore the type check
        # or cast (but it is currently banned in our linting rules). Better solution
        # would be discriminated union, but that requires the discriminator to be part
        # of the properties (not outside on the parent model).
        return self.properties


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
