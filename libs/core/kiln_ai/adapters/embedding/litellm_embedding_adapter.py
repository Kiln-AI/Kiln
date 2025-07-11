from functools import cached_property
from typing import List

import litellm
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


class LitellmEmbeddingAdapter(BaseEmbeddingAdapter):
    def __init__(self, embedding_config: EmbeddingConfig):
        super().__init__(embedding_config)

    async def _generate_embeddings(self, input_texts: List[str]) -> EmbeddingResult:
        # TODO: providers will throw if the text input is too long - goes over the max tokens for the model
        # we should validate that upstream to prevent this from bricking the whole pipeline if the user's dataset
        # happens to include chunks that are too long.

        # documented on litellm: https://docs.litellm.ai/docs/embedding/supported_embedding
        if len(input_texts) > MAX_BATCH_SIZE:
            raise ValueError("Text is too long")

        # docs: https://docs.litellm.ai/docs/embedding/supported_embedding
        response = await litellm.aembedding(
            model=self.litellm_model_id,
            input=input_texts,
            **self.build_options().model_dump(exclude_none=True),
        )

        # sanity check to ensure integrity as we should always have as many embeddings
        # as inputs
        if len(response.data) != len(input_texts):
            raise ValueError("Response data length does not match input text length")

        embeddings = []
        for item in sorted(response.data, key=lambda x: x.get("index")):
            embeddings.append(Embedding(vector=item.get("embedding")))

        return EmbeddingResult(embeddings=embeddings, usage=response.usage)

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
