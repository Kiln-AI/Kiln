from typing import List

import litellm
from pydantic import BaseModel, Field

from kiln_ai.adapters.embedding.base_embedding_adapter import (
    BaseEmbeddingAdapter,
    EmbeddingResult,
    GeneratedEmbedding,
)
from kiln_ai.datamodel.embedding import EmbeddingConfig

MAX_BATCH_SIZE = 2048


class EmbeddingOptions(BaseModel):
    dimensions: int | None = Field(
        default=None,
        description="Some models support requesting vectors of different dimensions.",
    )


class LitellmEmbeddingAdapter(BaseEmbeddingAdapter):
    def __init__(self, embedding_config: EmbeddingConfig):
        model_provider = embedding_config.model_provider
        if model_provider is None:
            raise ValueError("Provider must be set")

        model_name = embedding_config.model_name
        if model_name is None:
            raise ValueError("Model name must be set")

        super().__init__(embedding_config)
        self.model_provider = model_provider
        self.model_name = model_name
        self.properties = embedding_config.properties

    async def _embed(self, text: List[str]) -> EmbeddingResult:
        # TODO: providers will throw if the text input is too long - goes over the max tokens for the model
        # we should validate that upstream to prevent this from bricking the whole pipeline if the user's dataset
        # happens to include chunks that are too long.

        # documented on litellm: https://docs.litellm.ai/docs/embedding/supported_embedding
        if len(text) > MAX_BATCH_SIZE:
            raise ValueError("Text is too long")

        # docs: https://docs.litellm.ai/docs/embedding/supported_embedding
        response = await litellm.aembedding(
            model=self.model_name,
            input=text,
            encoding_format="float",
            **self.build_options().model_dump(exclude_none=True),
        )

        # sanity check to ensure integrity as we should always have as many embeddings
        # as inputs
        if len(response.data) != len(text):
            raise ValueError("Response data length does not match input text length")

        embeddings = []
        for item in sorted(response.data, key=lambda x: x.index):
            embeddings.append(GeneratedEmbedding(vector=item.embedding))

        return EmbeddingResult(embeddings=embeddings, usage=response.usage)

    def build_options(self) -> EmbeddingOptions:
        dimensions = self.properties.get("dimensions", None)
        if dimensions is not None and not isinstance(dimensions, int):
            raise ValueError("Dimensions must be an integer")

        return EmbeddingOptions(
            dimensions=dimensions,
        )
