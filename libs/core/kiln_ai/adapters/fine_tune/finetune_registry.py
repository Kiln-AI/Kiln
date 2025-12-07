from __future__ import annotations

from typing import TYPE_CHECKING, Type

from kiln_ai.adapters.fine_tune.base_finetune import BaseFinetuneAdapter
from kiln_ai.adapters.fine_tune.fireworks_finetune import FireworksFinetune
from kiln_ai.adapters.fine_tune.openai_finetune import OpenAIFinetune
from kiln_ai.adapters.fine_tune.together_finetune import TogetherFinetune
from kiln_ai.adapters.ml_model_list import ModelProviderName
from kiln_ai.utils.optional_deps import lazy_import

if TYPE_CHECKING:
    from kiln_ai.adapters.fine_tune.vertex_finetune import VertexFinetune

# Registry of finetune adapters that don't require optional dependencies
_base_finetune_registry: dict[ModelProviderName, Type[BaseFinetuneAdapter]] = {
    ModelProviderName.openai: OpenAIFinetune,
    ModelProviderName.fireworks_ai: FireworksFinetune,
    ModelProviderName.together_ai: TogetherFinetune,
}

# All supported providers (for membership checks)
_all_finetune_providers: set[ModelProviderName] = {
    ModelProviderName.openai,
    ModelProviderName.fireworks_ai,
    ModelProviderName.together_ai,
    ModelProviderName.vertex,
}


def get_finetune_adapter_class(
    provider: ModelProviderName,
) -> Type[BaseFinetuneAdapter]:
    """
    Get the finetune adapter class for a provider.

    Args:
        provider: The model provider name

    Returns:
        The finetune adapter class for the provider

    Raises:
        KeyError: If the provider is not supported for fine-tuning
        MissingDependencyError: If optional dependencies are missing (e.g., vertex)
    """
    if provider in _base_finetune_registry:
        return _base_finetune_registry[provider]

    if provider == ModelProviderName.vertex:
        mod = lazy_import("kiln_ai.adapters.fine_tune.vertex_finetune", "vertex")
        VertexFinetune: type[VertexFinetune] = mod.VertexFinetune
        return VertexFinetune

    raise KeyError(f"No finetune adapter found for provider: {provider}")


def is_finetune_provider_supported(provider: ModelProviderName) -> bool:
    """Check if a provider supports fine-tuning."""
    return provider in _all_finetune_providers


# Backwards compatibility: dict-like interface
# This allows existing code using `finetune_registry[provider]` to continue working
class _FinetuneRegistryCompat:
    """Dict-like wrapper that provides lazy loading for optional dependencies."""

    def _normalize_provider(
        self, provider: ModelProviderName | str
    ) -> ModelProviderName:
        """Convert string to ModelProviderName if needed."""
        if isinstance(provider, str):
            return ModelProviderName(provider)
        return provider

    def __getitem__(
        self, provider: ModelProviderName | str
    ) -> Type[BaseFinetuneAdapter]:
        return get_finetune_adapter_class(self._normalize_provider(provider))

    def __contains__(self, provider: object) -> bool:
        if isinstance(provider, str):
            try:
                provider = ModelProviderName(provider)
            except ValueError:
                return False
        if not isinstance(provider, ModelProviderName):
            return False
        return is_finetune_provider_supported(provider)

    def get(
        self,
        provider: ModelProviderName | str,
        default: Type[BaseFinetuneAdapter] | None = None,
    ) -> Type[BaseFinetuneAdapter] | None:
        try:
            return get_finetune_adapter_class(self._normalize_provider(provider))
        except (KeyError, ValueError):
            return default


finetune_registry = _FinetuneRegistryCompat()
