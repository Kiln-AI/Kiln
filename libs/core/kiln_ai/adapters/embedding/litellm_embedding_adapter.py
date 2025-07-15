from functools import cached_property
from typing import List, Tuple

import litellm
from litellm.types.utils import EmbeddingResponse
from pydantic import BaseModel, Field

from kiln_ai.adapters.embedding.base_embedding_adapter import (
    BaseEmbeddingAdapter,
    Embedding,
    EmbeddingResult,
)
from kiln_ai.adapters.ml_embedding_model_list import (
    KilnEmbeddingModelProvider,
    built_in_embedding_models_from_provider,
)
from kiln_ai.datamodel.embedding import EmbeddingConfig
from kiln_ai.utils.litellm import get_litellm_provider_info

MAX_BATCH_SIZE = 2048


class EmbeddingOptions(BaseModel):
    dimensions: int | None = Field(
        default=None,
        description="The number of dimensions to return for embeddings. Some models support requesting vectors of different dimensions.",
    )


def validate_map_to_embeddings(
    response: EmbeddingResponse,
    expected_embedding_count: int,
) -> List[Embedding]:
    # LiteLLM has an Embedding type in litellm.types.utils, but the EmbeddingResponse data has a list of untyped dicts,
    # which can be dangerous especially if we upgrade litellm, so we do some sanity checks here
    if not isinstance(response, EmbeddingResponse):
        raise RuntimeError(f"Expected EmbeddingResponse, got {type(response)}.")

    list_to_validate = response.data
    if len(list_to_validate) != expected_embedding_count:
        raise RuntimeError(
            f"Expected the number of embeddings in the response to be {expected_embedding_count}, got {len(list_to_validate)}."
        )

    validated_vectors: List[Tuple[list[float], int]] = []
    for embedding_dict in list_to_validate:
        object_type = embedding_dict.get("object")
        if object_type != "embedding":
            raise RuntimeError(
                f"Embedding response data has an unexpected shape. Property 'object' is not 'embedding'. Got {object_type}."
            )

        embedding_property_value = embedding_dict.get("embedding")
        if embedding_property_value is None:
            raise RuntimeError(
                "Embedding response data has an unexpected shape. Property 'embedding' is None in response data item."
            )
        if not isinstance(embedding_property_value, list):
            raise RuntimeError(
                f"Embedding response data has an unexpected shape. Property 'embedding' is not a list. Got {type(embedding_property_value)}."
            )

        index_property_value = embedding_dict.get("index")
        if index_property_value is None:
            raise RuntimeError(
                "Embedding response data has an unexpected shape. Property 'index' is None in response data item."
            )
        if not isinstance(index_property_value, int):
            raise RuntimeError(
                f"Embedding response data has an unexpected shape. Property 'index' is not an integer. Got {type(index_property_value)}."
            )

        validated_vectors.append((embedding_property_value, index_property_value))

    # sort by index, in place - the data should already be sorted by index,
    # but litellm docs are not explicit about this
    validated_vectors.sort(key=lambda x: x[1])

    return [
        Embedding(vector=embedding_vector) for embedding_vector, _ in validated_vectors
    ]


class LitellmEmbeddingAdapter(BaseEmbeddingAdapter):
    def __init__(self, embedding_config: EmbeddingConfig):
        super().__init__(embedding_config)

    async def _generate_embeddings(self, input_texts: List[str]) -> EmbeddingResult:
        # documented on litellm: https://docs.litellm.ai/docs/embedding/supported_embedding
        if len(input_texts) > MAX_BATCH_SIZE:
            raise ValueError("Text is too long")

        response = await litellm.aembedding(
            model=self.litellm_model_id,
            input=input_texts,
            **self.build_options().model_dump(exclude_none=True),
        )

        validated_embeddings = validate_map_to_embeddings(
            response, expected_embedding_count=len(input_texts)
        )

        return EmbeddingResult(
            embeddings=validated_embeddings,
            usage=response.usage,
        )

    def build_options(self) -> EmbeddingOptions:
        dimensions = self.embedding_config.properties.get("dimensions", None)
        if dimensions is not None:
            if not isinstance(dimensions, int) or dimensions <= 0:
                raise ValueError("Dimensions must be a positive integer")

        return EmbeddingOptions(
            dimensions=dimensions,
        )

    @cached_property
    def model_provider(self) -> KilnEmbeddingModelProvider:
        provider = built_in_embedding_models_from_provider(
            self.embedding_config.model_provider_name, self.embedding_config.model_name
        )
        if provider is None:
            raise ValueError(
                f"Embedding model {self.embedding_config.model_name} not found in the list of built-in models"
            )
        return provider

    @cached_property
    def litellm_model_id(self) -> str:
        provider_info = get_litellm_provider_info(self.model_provider)
        if provider_info.is_custom:
            raise ValueError(
                f"Provider {self.model_provider.name} is not supported by litellm for embeddings"
            )

        return provider_info.litellm_model_id
