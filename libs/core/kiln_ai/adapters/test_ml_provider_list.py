import re
from unittest.mock import patch

import pytest

from kiln_ai.adapters.ml_provider_list import (
    KilnProviderInfo,
    built_in_providers,
    get_provider_info,
)
from kiln_ai.adapters.model_agent_info import PROVIDER_LIST_TAGS
from kiln_ai.adapters.test_model_agent_info import (
    assert_valid_note,
    assert_valid_tags,
)
from kiln_ai.datamodel.datamodel_enums import ModelProviderName

MODELS_DEV_ID_PATTERN = re.compile(r"^[a-z0-9-]+$")


def test_one_item_per_provider_in_enum_order():
    assert [p.id for p in built_in_providers] == list(ModelProviderName)


@pytest.mark.parametrize("info", built_in_providers, ids=lambda p: p.id.value)
def test_provider_info_follows_rules(info: KilnProviderInfo):
    assert info.friendly_name.strip()
    assert info.models_dev_id is None or MODELS_DEV_ID_PATTERN.match(info.models_dev_id)
    assert_valid_tags(info.tags, PROVIDER_LIST_TAGS)
    assert_valid_note(info.notes)


@pytest.mark.parametrize("provider", list(ModelProviderName))
def test_get_provider_info_returns_item(provider: ModelProviderName):
    info = get_provider_info(provider)
    assert info.id == provider


def test_get_provider_info_raises_for_missing_provider():
    with patch("kiln_ai.adapters.ml_provider_list.built_in_providers", ()):
        with pytest.raises(ValueError, match="No provider info for openai"):
            get_provider_info(ModelProviderName.openai)


def test_models_dev_ids():
    models_dev_ids = {p.id: p.models_dev_id for p in built_in_providers}
    # Hugging Face maps to models.dev's `huggingface` key once that is confirmed to be
    # the same service; until then it has no mapping.
    assert models_dev_ids.pop(ModelProviderName.huggingface) in (None, "huggingface")
    assert models_dev_ids == {
        ModelProviderName.openai: "openai",
        ModelProviderName.anthropic: "anthropic",
        ModelProviderName.gemini_api: "google",
        ModelProviderName.vertex: "google-vertex",
        ModelProviderName.openrouter: "openrouter",
        ModelProviderName.groq: "groq",
        ModelProviderName.amazon_bedrock: "amazon-bedrock",
        ModelProviderName.azure_openai: "azure",
        ModelProviderName.fireworks_ai: "fireworks-ai",
        ModelProviderName.together_ai: "togetherai",
        ModelProviderName.siliconflow_cn: "siliconflow-cn",
        ModelProviderName.cerebras: "cerebras",
        ModelProviderName.cloudflare: "cloudflare-workers-ai",
        ModelProviderName.featherless_ai: None,
        ModelProviderName.typesafe: None,
        ModelProviderName.ollama: None,
        ModelProviderName.docker_model_runner: None,
        ModelProviderName.kiln_fine_tune: None,
        ModelProviderName.kiln_custom_registry: None,
        ModelProviderName.openai_compatible: None,
    }
