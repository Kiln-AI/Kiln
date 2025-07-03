from enum import Enum
from typing import List

from pydantic import BaseModel, Field

from kiln_ai.datamodel.datamodel_enums import ModelProviderName


class KilnEmbeddingModelFamily(str, Enum):
    """
    Enumeration of supported embedding model families.
    """

    # for bespoke proprietary models, the family tends to be the same
    # as provider name, but it does not have to be
    openai = "openai"
    gemini = "gemini"


class EmbeddingModelName(str, Enum):
    """
    Enumeration of specific model versions supported by the system.
    """

    # Embedding models
    openai_text_embedding_3 = "openai_text_embedding_3"
    gemini_text_embedding_004 = "gemini_text_embedding_004"


class KilnEmbeddingModelProvider(BaseModel):
    name: ModelProviderName

    model_id: str | None = None

    max_input_tokens: int | None = None

    supported_dimensions: List[int] | None = Field(
        default=None,
        description="The number of dimensions in the output embedding. If the model allows picking between different options, provide the list of available dimensions.",
    )

    supports_custom_dimensions: bool = Field(
        default=False,
        description="Whether the model supports setting a custom output dimension. If true, the user can set the output dimension in the UI.",
    )


class KilnEmbeddingModel(BaseModel):
    """
    Configuration for a specific embedding model.
    """

    family: KilnEmbeddingModelFamily
    name: str
    friendly_name: str
    providers: List[KilnEmbeddingModelProvider]


embedding_models: List[KilnEmbeddingModel] = [
    KilnEmbeddingModel(
        family=KilnEmbeddingModelFamily.openai,
        name=EmbeddingModelName.openai_text_embedding_3,
        friendly_name="text-embedding-3",
        providers=[
            KilnEmbeddingModelProvider(
                # TODO: wondering if should use separate enum for the ModelProviderName,
                # but since the hooking up of providers is global, maybe reusing is
                # best?
                name=ModelProviderName.openai,
                model_id="text-embedding-3",
                supports_custom_dimensions=True,
                max_input_tokens=8192,
            ),
        ],
    ),
    KilnEmbeddingModel(
        family=KilnEmbeddingModelFamily.gemini,
        name=EmbeddingModelName.gemini_text_embedding_004,
        friendly_name="text-embedding-004",
        providers=[
            KilnEmbeddingModelProvider(
                name=ModelProviderName.gemini_api,
                model_id="text-embedding-004",
                supported_dimensions=[768],
                max_input_tokens=2048,
            ),
        ],
    ),
]


def get_model_by_name(name: EmbeddingModelName) -> KilnEmbeddingModel:
    for model in embedding_models:
        if model.name == name:
            return model
    raise ValueError(f"Embedding model {name} not found in the list of built-in models")
