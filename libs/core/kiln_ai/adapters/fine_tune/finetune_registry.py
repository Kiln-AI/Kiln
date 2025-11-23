from typing import Type

from kiln_ai.adapters.fine_tune.base_finetune import BaseFinetuneAdapter
from kiln_ai.adapters.fine_tune.fireworks_finetune import FireworksFinetune
from kiln_ai.adapters.fine_tune.openai_finetune import OpenAIFinetune
from kiln_ai.adapters.fine_tune.together_finetune import TogetherFinetune
from kiln_ai.adapters.ml_model_list import ModelProviderName


def get_finetune_adapter_class(
    provider_name: ModelProviderName,
) -> Type[BaseFinetuneAdapter]:
    """Get the finetune adapter class for a given provider, handling optional dependencies."""
    if provider_name == ModelProviderName.openai:
        return OpenAIFinetune
    elif provider_name == ModelProviderName.fireworks_ai:
        return FireworksFinetune
    elif provider_name == ModelProviderName.together_ai:
        return TogetherFinetune
    elif provider_name == ModelProviderName.vertex:
        from kiln_ai.adapters.fine_tune.vertex_finetune import VertexFinetune

        return VertexFinetune
    else:
        raise ValueError(f"Unsupported provider: {provider_name}")


# For backward compatibility, create a module-level registry that works lazily
class _FinetuneRegistry:
    """Lazy registry that only imports optional adapters when accessed."""

    def __getitem__(self, key: ModelProviderName) -> Type[BaseFinetuneAdapter]:
        if key == ModelProviderName.openai:
            return OpenAIFinetune
        elif key == ModelProviderName.fireworks_ai:
            return FireworksFinetune
        elif key == ModelProviderName.together_ai:
            return TogetherFinetune
        elif key == ModelProviderName.vertex:
            return get_finetune_adapter_class(ModelProviderName.vertex)
        else:
            raise ValueError(f"Unsupported provider: {key}")

    def get(self, key: ModelProviderName, default=None):
        try:
            return self[key]
        except (ValueError, KeyError):
            return default


finetune_registry = _FinetuneRegistry()
