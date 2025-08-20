from enum import Enum
from typing import TYPE_CHECKING, Union

from pydantic import BaseModel, Field, model_validator

from kiln_ai.datamodel.basemodel import FilenameString, KilnParentedModel

if TYPE_CHECKING:
    from kiln_ai.datamodel.project import Project


class VectorStoreType(str, Enum):
    LANCE_DB = "lancedb"
    CHROMA = "chroma"
    QDRANT = "qdrant"


class LanceDBTableSchemaVersion(str, Enum):
    V1 = "1"


class LanceDBVectorIndexType(str, Enum):
    BRUTEFORCE = "bruteforce"


class QdrantVectorIndexType(str, Enum):
    BRUTEFORCE = "bruteforce"


class LanceDBVectorIndexMetric(str, Enum):
    DOT = "dot"
    COSINE = "cosine"
    L2 = "l2"


class QdrantVectorIndexMetric(str, Enum):
    COSINE = "Cosine"
    EUCLID = "Euclid"
    DOT = "Dot"
    MANHATTAN = "Manhattan"


class LanceDBConfigProperties(BaseModel):
    table_schema_version: LanceDBTableSchemaVersion
    vector_index_type: LanceDBVectorIndexType


class ChromaConfigProperties(BaseModel):
    pass


class WeaviateConfigProperties(BaseModel):
    pass


class QdrantConfigProperties(BaseModel):
    vector_index_type: QdrantVectorIndexType
    distance: QdrantVectorIndexMetric


class VectorStoreConfig(KilnParentedModel):
    name: FilenameString = Field(
        description="A name for your own reference to identify the vector store config.",
    )
    store_type: VectorStoreType = Field(
        description="The type of vector store to use.",
    )
    properties: dict[str, str | int] = Field(
        description="The properties of the vector store config, specific to the selected store_type.",
    )

    @model_validator(mode="after")
    def validate_properties(self):
        match self.store_type:
            case VectorStoreType.LANCE_DB:
                return self.validate_lance_db_properties()
            case VectorStoreType.CHROMA:
                return self.validate_chroma_properties()
            case VectorStoreType.QDRANT:
                return self.validate_qdrant_properties()
            case _:
                raise ValueError("Invalid vector store type")

    def validate_lance_db_properties(self):
        if "table_schema_version" not in self.properties or self.properties[
            "table_schema_version"
        ] not in [v.value for v in LanceDBTableSchemaVersion]:
            raise ValueError("LanceDB table schema version not found in properties")
        if "vector_index_type" not in self.properties or self.properties[
            "vector_index_type"
        ] not in [v.value for v in LanceDBVectorIndexType]:
            raise ValueError("LanceDB vector index type not found in properties")

        return self

    def lancedb_typed_properties(self) -> LanceDBConfigProperties:
        if self.store_type != VectorStoreType.LANCE_DB:
            raise ValueError(
                "lancedb_typed_properties can only be called for LanceDB vector store configs"
            )

        def safe_int(value) -> int | None:
            if value is None:
                return None
            return int(value)

        return LanceDBConfigProperties(
            table_schema_version=LanceDBTableSchemaVersion(
                self.properties.get("table_schema_version")
            ),
            vector_index_type=LanceDBVectorIndexType(
                self.properties.get("vector_index_type")
            ),
        )

    def validate_chroma_properties(self):
        # ChromaDB doesn't require specific properties for basic operation
        # but we can validate any properties that are provided
        return self

    def chroma_typed_properties(self) -> ChromaConfigProperties:
        if self.store_type != VectorStoreType.CHROMA:
            raise ValueError(
                "chroma_typed_properties can only be called for Chroma vector store configs"
            )
        return ChromaConfigProperties()

    def validate_qdrant_properties(self):
        if "vector_index_type" not in self.properties or self.properties[
            "vector_index_type"
        ] not in [v.value for v in QdrantVectorIndexType]:
            raise ValueError("Qdrant vector index type not found in properties")
        if "distance" not in self.properties or self.properties["distance"] not in [
            v.value for v in QdrantVectorIndexMetric
        ]:
            raise ValueError("Qdrant distance not found in properties")
        return self

    def qdrant_typed_properties(self) -> QdrantConfigProperties:
        if self.store_type != VectorStoreType.QDRANT:
            raise ValueError(
                "qdrant_typed_properties can only be called for Qdrant vector store configs"
            )

        def safe_int(value) -> int | None:
            if value is None:
                return None
            return int(value)

        return QdrantConfigProperties(
            vector_index_type=QdrantVectorIndexType(
                self.properties.get("vector_index_type")
            ),
            distance=QdrantVectorIndexMetric(self.properties.get("distance")),
        )

    # Workaround to return typed parent without importing Project
    def parent_project(self) -> Union["Project", None]:
        if self.parent is None or self.parent.__class__.__name__ != "Project":
            return None
        return self.parent  # type: ignore
