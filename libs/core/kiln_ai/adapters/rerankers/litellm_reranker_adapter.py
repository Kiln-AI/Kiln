from functools import cached_property

import litellm
from kiln_ai.adapters.provider_tools import LiteLlmCoreConfig
from kiln_ai.adapters.reranker_list import (
    KilnRerankerModelProvider,
    built_in_reranker_models_from_provider,
)
from kiln_ai.adapters.rerankers.base_reranker import (
    BaseReranker,
    RerankDocument,
    RerankResponse,
    RerankResult,
)
from kiln_ai.datamodel.datamodel_enums import ModelProviderName
from kiln_ai.datamodel.reranker import RerankerConfig
from kiln_ai.utils.litellm import get_litellm_provider_info


class LitellmRerankerAdapter(BaseReranker):
    def __init__(
        self,
        reranker_config: RerankerConfig,
        litellm_provider_config: LiteLlmCoreConfig,
    ):
        super().__init__(reranker_config)
        self.litellm_provider_config = litellm_provider_config

    async def rerank(
        self, query: str, documents: list[RerankDocument]
    ) -> RerankResponse:
        if len(documents) == 0:
            return RerankResponse(results=[])

        rerank_kwargs = {
            "model": self.litellm_model_slug,
            "query": query,
            "documents": [document.text for document in documents],
            "top_n": self.reranker_config.top_n,
        }

        if self.litellm_provider_config.base_url:
            rerank_kwargs["base_url"] = self.litellm_provider_config.base_url

        if self.litellm_provider_config.default_headers:
            rerank_kwargs["default_headers"] = (
                self.litellm_provider_config.default_headers
            )

        if self.litellm_provider_config.additional_body_options:
            rerank_kwargs.update(self.litellm_provider_config.additional_body_options)

        response = await litellm.arerank(**rerank_kwargs)
        if not isinstance(response, litellm.RerankResponse):
            raise ValueError(f"Expected RerankResponse, got {type(response)}")

        return self.convert_to_rerank_response(documents, response)

    def convert_to_rerank_response(
        self,
        original_candidates: list[RerankDocument],
        response: litellm.RerankResponse,
    ) -> RerankResponse:
        if not response.results:
            raise ValueError("No results returned from LiteLLM")

        results = []
        for result in response.results:
            idx = int(result.get("index"))
            if idx < 0 or idx >= len(original_candidates):
                raise ValueError(
                    f"Reranker returned invalid index {idx} (len={len(original_candidates)})"
                )
            document = original_candidates[idx]
            results.append(
                RerankResult(
                    document=document,
                    index=result["index"],
                    relevance_score=result["relevance_score"],
                )
            )

        return RerankResponse(results=results)

    @cached_property
    def model_provider(self) -> KilnRerankerModelProvider:
        kiln_reranker_model_provider = built_in_reranker_models_from_provider(
            ModelProviderName(self.reranker_config.model_provider_name),
            self.reranker_config.model_name,
        )
        if kiln_reranker_model_provider is None:
            raise ValueError(
                f"Reranker model {self.reranker_config.model_name} not found in the list of built-in reranker models"
            )
        return kiln_reranker_model_provider

    @cached_property
    def litellm_model_slug(self) -> str:
        litellm_provider_name = get_litellm_provider_info(
            self.model_provider,
        )
        return litellm_provider_name.litellm_model_id
