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

    # Embedding model names are often generic (e.g., "text-embedding"),
    # so we prefix them with the provider name (e.g., "openai_") to ensure
    # uniqueness across providers now and in the future
    openai_text_embedding_3_small = "openai_text_embedding_3_small"
    openai_text_embedding_3_large = "openai_text_embedding_3_large"
    gemini_text_embedding_004 = "gemini_text_embedding_004"


class KilnEmbeddingModelProvider(BaseModel):
    name: ModelProviderName

    model_id: str = Field(
        description="The model ID for the embedding model. This is the ID used to identify the model in the provider's API.",
    )

    max_input_tokens: int | None = Field(
        default=None,
        description="The maximum number of tokens that can be input to the model.",
    )

    n_dimensions: int = Field(
        description="The number of dimensions in the output embedding.",
    )

    supports_custom_dimensions: bool = Field(
        default=False,
        description="Whether the model supports setting a custom output dimension. If true, the user can set the output dimension in the UI.",
    )


class KilnEmbeddingModel(BaseModel):
    """
    Configuration for a specific embedding model.
    """

    family: str
    name: str
    friendly_name: str
    providers: List[KilnEmbeddingModelProvider]


built_in_embedding_models: List[KilnEmbeddingModel] = [
    KilnEmbeddingModel(
        family=KilnEmbeddingModelFamily.openai,
        name=EmbeddingModelName.openai_text_embedding_3_small,
        friendly_name="text-embedding-3-small",
        providers=[
            KilnEmbeddingModelProvider(
                name=ModelProviderName.openai,
                model_id="text-embedding-3-small",
                n_dimensions=1536,
                max_input_tokens=8192,
                supports_custom_dimensions=True,
            ),
        ],
    ),
    KilnEmbeddingModel(
        family=KilnEmbeddingModelFamily.openai,
        name=EmbeddingModelName.openai_text_embedding_3_large,
        friendly_name="text-embedding-3-large",
        providers=[
            KilnEmbeddingModelProvider(
                name=ModelProviderName.openai,
                model_id="text-embedding-3-large",
                n_dimensions=3072,
                max_input_tokens=8192,
                supports_custom_dimensions=True,
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
                n_dimensions=768,
                max_input_tokens=2048,
            ),
        ],
    ),
]


def get_model_by_name(name: EmbeddingModelName) -> KilnEmbeddingModel:
    for model in built_in_embedding_models:
        if model.name == name:
            return model
    raise ValueError(f"Embedding model {name} not found in the list of built-in models")


def built_in_embedding_models_from_provider(
    provider_name: ModelProviderName, model_name: str
) -> KilnEmbeddingModelProvider | None:
    for model in built_in_embedding_models:
        if model.name == model_name:
            for p in model.providers:
                if p.name == provider_name:
                    return p
    return None
