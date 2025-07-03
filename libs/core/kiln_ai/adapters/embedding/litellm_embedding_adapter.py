from typing import List

import litellm
from pydantic import BaseModel, Field

from kiln_ai.adapters.embedding.base_embedding_adapter import (
    BaseEmbeddingAdapter,
    EmbeddingResult,
    GeneratedEmbedding,
)
from kiln_ai.adapters.ml_embedding_model_list import (
    KilnEmbeddingModelProvider,
    built_in_embedding_models_from_provider,
)
from kiln_ai.datamodel.datamodel_enums import ModelProviderName
from kiln_ai.datamodel.embedding import EmbeddingConfig
from kiln_ai.utils.exhaustive_error import raise_exhaustive_enum_error

MAX_BATCH_SIZE = 2048


class EmbeddingOptions(BaseModel):
    dimensions: int | None = Field(
        default=None,
        description="Some models support requesting vectors of different dimensions.",
    )


class LitellmEmbeddingAdapter(BaseEmbeddingAdapter):
    def __init__(self, embedding_config: EmbeddingConfig):
        model_provider_name = embedding_config.model_provider_name
        if model_provider_name is None:
            raise ValueError("Provider must be set")

        model_name = embedding_config.model_name
        if model_name is None:
            raise ValueError("Model name must be set")

        super().__init__(embedding_config)
        self.model_provider_name = model_provider_name
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
            model=self.litellm_model_id(),
            input=text,
            **self.build_options().model_dump(exclude_none=True),
        )

        # sanity check to ensure integrity as we should always have as many embeddings
        # as inputs
        if len(response.data) != len(text):
            raise ValueError("Response data length does not match input text length")

        embeddings = []
        for item in sorted(response.data, key=lambda x: x.get("index")):
            embeddings.append(GeneratedEmbedding(vector=item.get("embedding")))

        return EmbeddingResult(embeddings=embeddings, usage=response.usage)

    def build_options(self) -> EmbeddingOptions:
        dimensions = self.properties.get("dimensions", None)
        if dimensions is not None:
            if not isinstance(dimensions, int) or dimensions <= 0:
                raise ValueError("Dimensions must be a positive integer")

        return EmbeddingOptions(
            dimensions=dimensions,
        )

    def _resolve_model_provider(self) -> KilnEmbeddingModelProvider:
        model = built_in_embedding_models_from_provider(
            self.model_provider_name, self.model_name
        )
        if model is None:
            raise ValueError(
                f"Embedding model {self.model_name} not found in the list of built-in models"
            )
        return model

    # TODO: refactor this to be shared with other implementations of LiteLLM adapters
    # for example, embedding adapter for LiteLLM, and also Exractor adapter for LiteLLM
    def litellm_model_id(self) -> str:
        provider = self._resolve_model_provider()
        if not provider:
            raise ValueError("Model ID is required for OpenAI compatible models")

        litellm_provider_name: str | None = None
        provider_not_supported = False
        match provider.name:
            case ModelProviderName.openrouter:
                litellm_provider_name = "openrouter"
            case ModelProviderName.openai:
                litellm_provider_name = "openai"
            case ModelProviderName.groq:
                litellm_provider_name = "groq"
            case ModelProviderName.anthropic:
                litellm_provider_name = "anthropic"
            case ModelProviderName.gemini_api:
                litellm_provider_name = "gemini"
            case ModelProviderName.fireworks_ai:
                litellm_provider_name = "fireworks_ai"
            case ModelProviderName.amazon_bedrock:
                litellm_provider_name = "bedrock"
            case ModelProviderName.azure_openai:
                litellm_provider_name = "azure"
            case ModelProviderName.huggingface:
                litellm_provider_name = "huggingface"
            case ModelProviderName.vertex:
                litellm_provider_name = "vertex_ai"
            case ModelProviderName.together_ai:
                litellm_provider_name = "together_ai"
            case ModelProviderName.openai_compatible:
                provider_not_supported = True
            case ModelProviderName.kiln_custom_registry:
                provider_not_supported = True
            case ModelProviderName.kiln_fine_tune:
                provider_not_supported = True
            case ModelProviderName.ollama:
                provider_not_supported = True
            case _:
                raise_exhaustive_enum_error(provider.name)

        if provider_not_supported:
            raise ValueError(f"Provider {provider.name} is not supported by litellm")

        self._litellm_model_id = (
            str(litellm_provider_name) + "/" + str(provider.model_id)
        )

        print(f"litellm_model_id: {self._litellm_model_id}")

        return self._litellm_model_id
