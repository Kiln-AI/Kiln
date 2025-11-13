from enum import Enum
from typing import TYPE_CHECKING, Literal, Union

from pydantic import Field, PositiveInt, ValidationInfo, model_validator
from typing_extensions import TypedDict

from kiln_ai.datamodel.basemodel import FilenameString, KilnParentedModel

if TYPE_CHECKING:
    from kiln_ai.datamodel.project import Project


class VectorStoreType(str, Enum):
    LANCE_DB_FTS = "lancedb_fts"
    LANCE_DB_HYBRID = "lancedb_hybrid"
    LANCE_DB_VECTOR = "lancedb_vector"


class LanceDBConfigFTSProperties(TypedDict, total=True):
    store_type: Literal[VectorStoreType.LANCE_DB_FTS]
    similarity_top_k: PositiveInt
    overfetch_factor: PositiveInt
    vector_column_name: str
    text_key: str
    doc_id_key: str


class LanceDBConfigVectorProperties(TypedDict, total=True):
    store_type: Literal[VectorStoreType.LANCE_DB_VECTOR]
    similarity_top_k: PositiveInt
    overfetch_factor: PositiveInt
    vector_column_name: str
    text_key: str
    doc_id_key: str
    nprobes: PositiveInt


class LanceDBConfigHybridProperties(LanceDBConfigVectorProperties, total=True):
    store_type: Literal[VectorStoreType.LANCE_DB_HYBRID]
    # no additional properties for hybrid, it is the same as the vector properties
    pass


class VectorStoreConfig(KilnParentedModel):
    name: FilenameString = Field(
        description="A name for your own reference to identify the vector store config.",
    )
    description: str | None = Field(
        description="A description for your own reference.",
        default=None,
    )
    store_type: VectorStoreType = Field(
        description="The type of vector store to use.",
    )
    properties: (
        LanceDBConfigFTSProperties
        | LanceDBConfigVectorProperties
        | LanceDBConfigHybridProperties
    ) = Field(
        description="The properties of the vector store config, specific to the selected store_type.",
        # the discriminator refers to the properties->store_type key (not the store_type field on the parent model)
        discriminator="store_type",
    )

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
        # - we originally did not have the store_type in the properties, so we need to add it here
        # - we started wanted to have store_type in the properties to use pydantic's discriminated union feature
        properties = data.get("properties", {})
        if "store_type" not in properties:
            # the store_type on the parent model is always there, we just need to add it to the properties
            properties["store_type"] = data["store_type"]
            data["properties"] = properties
        return data

    @model_validator(mode="after")
    def ensure_store_type_matches_properties(self):
        # sanity check to ensure the store_type matches the properties store_type
        if self.store_type != self.properties["store_type"]:
            raise ValueError(
                f"Store type mismatch: {self.store_type} != {self.properties['store_type']}. This is a bug, please report it."
            )
        return self

    @property
    def lancedb_vector_properties(self) -> LanceDBConfigVectorProperties:
        if self.properties["store_type"] != VectorStoreType.LANCE_DB_VECTOR:
            raise ValueError(
                f"Lancedb vector properties are only available for LanceDB vector store type. Got {self.properties.get('store_type')}"
            )
        return self.properties

    @property
    def lancedb_hybrid_properties(self) -> LanceDBConfigHybridProperties:
        if self.properties["store_type"] != VectorStoreType.LANCE_DB_HYBRID:
            raise ValueError(
                f"Lancedb hybrid properties are only available for LanceDB hybrid store type. Got {self.properties.get('store_type')}"
            )
        return self.properties

    @property
    def lancedb_fts_properties(self) -> LanceDBConfigFTSProperties:
        if self.properties["store_type"] != VectorStoreType.LANCE_DB_FTS:
            raise ValueError(
                f"Lancedb FTS properties are only available for LanceDB FTS store type. Got {self.properties.get('store_type')}"
            )
        return self.properties

    # Workaround to return typed parent without importing Project
    def parent_project(self) -> Union["Project", None]:
        if self.parent is None or self.parent.__class__.__name__ != "Project":
            return None
        return self.parent  # type: ignore
