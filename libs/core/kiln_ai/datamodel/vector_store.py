from enum import Enum
from typing import TYPE_CHECKING, Union

from pydantic import BaseModel, Field, model_validator

from kiln_ai.datamodel.basemodel import NAME_FIELD, KilnParentedModel

if TYPE_CHECKING:
    from kiln_ai.datamodel.project import Project


class VectorStoreType(str, Enum):
    LANCE_DB = "lancedb"


class LanceDBTableSchemaVersion(str, Enum):
    V1 = "1"


class LanceDBConfigProperties(BaseModel):
    path: str
    table_schema_version: LanceDBTableSchemaVersion
    vector_dimensions: int


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
            case _:
                raise ValueError("Invalid vector store type")

    def validate_lance_db_properties(self):
        # some of the options we could add: https://lancedb.github.io/lancedb/guides/storage/#general-configuration
        if "path" not in self.properties:
            raise ValueError("LanceDB path not found in properties")
        if "table_schema_version" not in self.properties or self.properties[
            "table_schema_version"
        ] not in [v.value for v in LanceDBTableSchemaVersion]:
            raise ValueError("LanceDB table schema version not found in properties")
        if "vector_dimensions" not in self.properties or not isinstance(
            self.properties["vector_dimensions"], int
        ):
            raise ValueError("LanceDB vector dimensions not found in properties")
        return self

    def lancedb_typed_properties(self) -> LanceDBConfigProperties:
        return LanceDBConfigProperties(
            path=str(self.properties["path"]),
            table_schema_version=LanceDBTableSchemaVersion(
                self.properties["table_schema_version"]
            ),
            vector_dimensions=int(self.properties["vector_dimensions"]),
        )

    # Workaround to return typed parent without importing Project
    def parent_project(self) -> Union["Project", None]:
        if self.parent is None or self.parent.__class__.__name__ != "Project":
            return None
        return self.parent  # type: ignore
