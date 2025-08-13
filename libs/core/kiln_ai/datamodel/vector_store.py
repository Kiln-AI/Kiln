from enum import Enum
from typing import TYPE_CHECKING, Union

from pydantic import BaseModel, Field, model_validator

from kiln_ai.datamodel.basemodel import NAME_FIELD, KilnParentedModel

if TYPE_CHECKING:
    from kiln_ai.datamodel.project import Project


class VectorStoreType(str, Enum):
    LANCE_DB = "lancedb"
    CHROMA = "chroma"
    WEAVIATE = "weaviate"


class LanceDBTableSchemaVersion(str, Enum):
    V1 = "1"


class LanceDBVectorIndexType(str, Enum):
    HNSW = "hnsw"
    BRUTEFORCE = "bruteforce"


class LanceDBVectorIndexMetric(str, Enum):
    DOT = "dot"
    COSINE = "cosine"
    L2 = "l2"


class LanceDBConfigProperties(BaseModel):
    table_schema_version: LanceDBTableSchemaVersion
    vector_index_type: LanceDBVectorIndexType

    # HNSW specific properties - https://lancedb.github.io/lancedb/concepts/index_hnsw/#k-nearest-neighbor-graphs-and-k-approximate-nearest-neighbor-graphs
    hnsw_distance_type: LanceDBVectorIndexMetric | None
    hnsw_m: int | None
    hnsw_ef_construction: int | None


class ChromaConfigProperties(BaseModel):
    pass


class WeaviateConfigProperties(BaseModel):
    pass


class VectorStoreConfig(KilnParentedModel):
    name: str = NAME_FIELD
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
            case VectorStoreType.WEAVIATE:
                return self.validate_weaviate_properties()
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

        # HNSW specific properties
        if self.properties["vector_index_type"] == LanceDBVectorIndexType.HNSW:
            if (
                "hnsw_m" not in self.properties
                or "hnsw_ef_construction" not in self.properties
                or "hnsw_distance_type" not in self.properties
            ):
                raise ValueError("HNSW specific properties not found in properties")
            if self.properties["hnsw_distance_type"] not in [
                v.value for v in LanceDBVectorIndexMetric
            ]:
                raise ValueError("HNSW distance type not found in properties")
            if self.properties["hnsw_m"] is None or not isinstance(
                self.properties["hnsw_m"], int
            ):
                raise ValueError("HNSW m must be a positive integer")
            if self.properties["hnsw_ef_construction"] is None or not isinstance(
                self.properties["hnsw_ef_construction"], int
            ):
                raise ValueError("HNSW ef_construction must be a positive integer")

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

        # Get HNSW properties only if they exist
        hnsw_distance_type = None
        hnsw_m = None
        hnsw_ef_construction = None

        if self.properties.get("hnsw_distance_type"):
            hnsw_distance_type = LanceDBVectorIndexMetric(
                self.properties.get("hnsw_distance_type")
            )
        if self.properties.get("hnsw_m"):
            hnsw_m = safe_int(self.properties.get("hnsw_m"))
        if self.properties.get("hnsw_ef_construction"):
            hnsw_ef_construction = safe_int(self.properties.get("hnsw_ef_construction"))

        return LanceDBConfigProperties(
            table_schema_version=LanceDBTableSchemaVersion(
                self.properties.get("table_schema_version")
            ),
            vector_index_type=LanceDBVectorIndexType(
                self.properties.get("vector_index_type")
            ),
            # hnsw specific properties
            hnsw_distance_type=hnsw_distance_type,
            hnsw_m=hnsw_m,
            hnsw_ef_construction=hnsw_ef_construction,
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

    def validate_weaviate_properties(self):
        return self

    def weaviate_typed_properties(self) -> WeaviateConfigProperties:
        if self.store_type != VectorStoreType.WEAVIATE:
            raise ValueError(
                "weaviate_typed_properties can only be called for Weaviate vector store configs"
            )
        return WeaviateConfigProperties()

    # Workaround to return typed parent without importing Project
    def parent_project(self) -> Union["Project", None]:
        if self.parent is None or self.parent.__class__.__name__ != "Project":
            return None
        return self.parent  # type: ignore
