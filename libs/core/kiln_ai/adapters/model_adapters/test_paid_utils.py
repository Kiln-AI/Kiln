import pytest

from kiln_ai.adapters.ml_model_list import ModelName
from kiln_ai.adapters.provider_tools import provider_warnings
from kiln_ai.utils.config import Config

# OpenAI-direct models whose tool calls LiteLLM sends to /v1/responses whenever
# reasoning is on. GPT-5.4 Pro and GPT-5.2 Pro are left out: LiteLLM sends every call
# for them to Responses, and test_tools_store_false_gpt_5_4_pro covers that path.
OPENAI_RESPONSES_TOOL_MODELS = [
    ModelName.gpt_5_4,
    ModelName.gpt_5_5,
    ModelName.gpt_5_6_sol,
    ModelName.gpt_5_6_terra,
    ModelName.gpt_5_6_luna,
    ModelName.gpt_6_astra,
    ModelName.gpt_6_sol,
    ModelName.gpt_6_luna,
    ModelName.gpt_6_1_sol,
    ModelName.gpt_6_1_terra,
]


def skip_if_missing_provider_keys(provider_name) -> None:
    warning = provider_warnings.get(provider_name)
    if warning is None:
        return
    missing = [
        key
        for key in warning.required_config_keys
        if not Config.shared().get_value(key)
    ]
    if missing:
        missing_list = ", ".join(missing)
        pytest.skip(
            f"Missing config keys for {provider_name}: {missing_list}. "
            "Set env vars or .env before running paid tests."
        )
