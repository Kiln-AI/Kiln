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
    TypeAdapter,
    field_serializer,
    model_validator,
)
from typing_extensions import TypedDict

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
    embedding_config_id: str
    buffer_size: PositiveInt
    breakpoint_percentile_threshold: PositiveInt
    include_metadata: bool
    include_prev_next_rel: bool


class FixedWindowChunkerProperties(TypedDict, total=True):
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

ChunkerConfigTypeAdapters = {
    ChunkerType.SEMANTIC: TypeAdapter(SemanticChunkerProperties),
    ChunkerType.FIXED_WINDOW: TypeAdapter(FixedWindowChunkerProperties),
}


class ChunkerConfig(
    # TODO: reenable - disabled to reenable typecheck
    KilnParentedModel
):
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
    )

    # Workaround to return typed parent without importing Project
    def parent_project(self) -> Union["Project", None]:
        if self.parent is None or self.parent.__class__.__name__ != "Project":
            return None
        return self.parent  # type: ignore

    @model_validator(mode="after")
    def validate_properties_matching_chunker_type(self) -> "ChunkerConfig":
        # at this point, the properties are already validated by the pydantic validator
        # but we have no guarantee we have the correct type of properties based on the chunker_type
        # so we need to check here that the properties are aligned with the chunker_type and we
        # are not getting fixed_window_properties when the chunker_type is semantic or vice versa
        try:
            ChunkerConfigTypeAdapters[self.chunker_type].validate_python(
                self.properties
            )
        except Exception as e:
            raise ValueError(
                f"The properties do not match the chunker type ({self.chunker_type}): {e}"
            ) from e
        return self

    # expose the typed properties based on the chunker_type
    @property
    def semantic_properties(self) -> SemanticChunkerProperties:
        if self.chunker_type != ChunkerType.SEMANTIC:
            raise ValueError(
                "Semantic properties are only available for semantic chunker."
            )
        # TypedDict cannot be checked at runtime, so we need to ignore the type check
        # or cast (but it is currently banned in our linting rules). Better solution
        # would be discriminated union, but that requires the discriminator to be part
        # of the properties (not outside on the parent model).
        return self.properties  # type: ignore

    @property
    def fixed_window_properties(self) -> FixedWindowChunkerProperties:
        if self.chunker_type != ChunkerType.FIXED_WINDOW:
            raise ValueError(
                "Fixed window properties are only available for fixed window chunker."
            )
        # TypedDict cannot be checked at runtime, so we need to ignore the type check
        # or cast (but it is currently banned in our linting rules). Better solution
        # would be discriminated union, but that requires the discriminator to be part
        # of the properties (not outside on the parent model).
        return self.properties  # type: ignore


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
