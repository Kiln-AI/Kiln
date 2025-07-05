from typing import TYPE_CHECKING, List, Union

from pydantic import BaseModel, Field, model_validator

from kiln_ai.datamodel.basemodel import ID_TYPE, NAME_FIELD, KilnParentedModel
from kiln_ai.datamodel.datamodel_enums import ModelProviderName

if TYPE_CHECKING:
    from kiln_ai.datamodel.chunk import ChunkedDocument
    from kiln_ai.datamodel.project import Project


class EmbeddingConfig(KilnParentedModel):
    name: str = NAME_FIELD
    description: str | None = Field(
        default=None, description="The description of the embedding config"
    )
    model_provider_name: ModelProviderName = Field(
        description="The provider to use to generate embeddings.",
    )
    # TODO: should model_name be the EmbeddingModelName enum instead of a string?
    # in the TaskRunConfigProperties, we store model_name as a plain string:
    # https://github.com/Kiln-AI/Kiln/blob/b92dde56d9259aa47ba4f71a820f90138bd86c6e/libs/core/kiln_ai/datamodel/task.py#L55
    # maybe for backward compatibility when we deprecate old models?
    model_name: str = Field(
        description="The model to use to generate embeddings.",
    )
    properties: dict[str, str | int | float | bool] = Field(
        description="Properties to be used to execute the embedding config.",
    )

    # Workaround to return typed parent without importing Project
    def parent_project(self) -> Union["Project", None]:
        if self.parent is None or self.parent.__class__.__name__ != "Project":
            return None
        return self.parent  # type: ignore

    @model_validator(mode="after")
    def validate_properties(self):
        # FIXME: not ideal to import here, but if we import normally, we get a circular import
        # We should probably move the ml model lists out of the adapters package, since they are
        # base constructs with no dependencies (and we seem to be getting a circular import due
        # to the __init__.py rather than due to intrinsic circularity)
        from kiln_ai.adapters.ml_embedding_model_list import (
            built_in_embedding_models_from_provider,
        )

        model_provider = built_in_embedding_models_from_provider(
            self.model_provider_name, self.model_name
        )

        if model_provider is None:
            raise ValueError(
                f"Model provider {self.model_provider_name} not found in the list of built-in models"
            )

        if "dimensions" in self.properties:
            if not model_provider.supports_custom_dimensions:
                raise ValueError(
                    f"The model {self.model_name} does not support custom dimensions"
                )
            if (
                not isinstance(self.properties["dimensions"], int)
                or self.properties["dimensions"] <= 0
            ):
                raise ValueError("Dimensions must be a positive integer")

        return self


class Embedding(BaseModel):
    vector: List[float] = Field(description="The vector of the embedding.")


class ChunkEmbeddings(KilnParentedModel):
    embedding_config_id: ID_TYPE = Field(
        description="The ID of the embedding config that was used to generate the embeddings.",
    )
    embeddings: List[Embedding] = Field(
        description="The embeddings of the chunks. The embedding at index i corresponds to the chunk at index i in the parent chunked document."
    )

    def parent_chunked_document(self) -> Union["ChunkedDocument", None]:
        if self.parent is None or self.parent.__class__.__name__ != "ChunkedDocument":
            return None
        return self.parent  # type: ignore
