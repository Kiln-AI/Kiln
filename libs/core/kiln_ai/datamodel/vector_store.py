from enum import Enum
from typing import TYPE_CHECKING, Union

from pydantic import BaseModel, Field, model_validator

from kiln_ai.datamodel.basemodel import FilenameString, KilnParentedModel
from kiln_ai.utils.exhaustive_error import raise_exhaustive_enum_error
from kiln_ai.utils.validation import (
    validate_return_dict_prop,
    validate_return_dict_prop_optional,
)

if TYPE_CHECKING:
    from kiln_ai.datamodel.project import Project


class VectorStoreType(str, Enum):
    LANCE_DB_FTS = "lancedb_fts"
    LANCE_DB_HYBRID = "lancedb_hybrid"
    LANCE_DB_VECTOR = "lancedb_vector"


class LanceDBConfigBaseProperties(BaseModel):
    similarity_top_k: int = Field(
        description="The number of results to return from the vector store.",
    )
    overfetch_factor: int = Field(
        description="The overfetch factor to use for the vector search.",
    )
    vector_column_name: str = Field(
        description="The name of the vector column in the vector store.",
    )
    text_key: str = Field(
        description="The name of the text column in the vector store.",
    )
    doc_id_key: str = Field(
        description="The name of the document id column in the vector store.",
    )
    nprobes: int | None = Field(
        description="The number of probes to use for the vector search.",
        default=None,
    )


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
    properties: dict[str, str | int | float | None] = Field(
        description="The properties of the vector store config, specific to the selected store_type.",
    )

    @model_validator(mode="after")
    def validate_properties(self):
        match self.store_type:
            case VectorStoreType.LANCE_DB_FTS:
                return self.validate_lancedb_properties(VectorStoreType.LANCE_DB_FTS)
            case VectorStoreType.LANCE_DB_HYBRID:
                return self.validate_lancedb_properties(VectorStoreType.LANCE_DB_HYBRID)
            case VectorStoreType.LANCE_DB_VECTOR:
                return self.validate_lancedb_properties(VectorStoreType.LANCE_DB_VECTOR)
            case _:
                raise_exhaustive_enum_error(self.store_type)

    def validate_lancedb_properties(self, store_type: VectorStoreType):
        validate_return_dict_prop(self.properties, "similarity_top_k", int)
        validate_return_dict_prop(self.properties, "overfetch_factor", int)
        validate_return_dict_prop(self.properties, "vector_column_name", str)
        validate_return_dict_prop(self.properties, "text_key", str)
        validate_return_dict_prop(self.properties, "doc_id_key", str)

        # nprobes is only used for vector and hybrid queries
        if (
            store_type == VectorStoreType.LANCE_DB_VECTOR
            or store_type == VectorStoreType.LANCE_DB_HYBRID
        ):
            validate_return_dict_prop(self.properties, "nprobes", int)

        return self

    @property
    def lancedb_properties(self) -> LanceDBConfigBaseProperties:
        return LanceDBConfigBaseProperties(
            similarity_top_k=validate_return_dict_prop(
                self.properties, "similarity_top_k", int
            ),
            overfetch_factor=validate_return_dict_prop(
                self.properties, "overfetch_factor", int
            ),
            vector_column_name=validate_return_dict_prop(
                self.properties, "vector_column_name", str
            ),
            text_key=validate_return_dict_prop(self.properties, "text_key", str),
            doc_id_key=validate_return_dict_prop(self.properties, "doc_id_key", str),
            nprobes=validate_return_dict_prop_optional(self.properties, "nprobes", int),
        )

    # Workaround to return typed parent without importing Project
    def parent_project(self) -> Union["Project", None]:
        if self.parent is None or self.parent.__class__.__name__ != "Project":
            return None
        return self.parent  # type: ignore
