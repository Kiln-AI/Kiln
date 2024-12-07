from typing import Type

from kiln_ai.adapters.fine_tune.base_finetune import BaseFinetuneAdapter
from kiln_ai.adapters.fine_tune.fireworks_finetune import FireworksFinetune
from kiln_ai.adapters.fine_tune.openai_finetune import OpenAIFinetune
from kiln_ai.adapters.ml_model_list import ModelProviderName

finetune_registry: dict[ModelProviderName, Type[BaseFinetuneAdapter]] = {
    ModelProviderName.openai: OpenAIFinetune,
    ModelProviderName.fireworks_ai: FireworksFinetune,
}
