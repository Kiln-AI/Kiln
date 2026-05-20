"""Curated whitelists for the @pytest.mark.prerelease smoke set.

Several paid tests (embeddings, document extraction, thinking levels) fan out
across every (model, provider) combination in ml_model_list.py. Running the
full fan-out under --runprerelease would be slow and expensive. These
whitelists are the "main highlights" — a handful of representative models
per family/provider that the sibling prerelease tests parametrize over.

Bias toward latest small / mini models per family for speed and cost. Touch
every major provider at least once. If you add a new family/provider, widen
the relevant list here rather than tagging an unrelated test as prerelease.
"""

from kiln_ai.datamodel.datamodel_enums import ModelProviderName
from kiln_ai.pytest_mock_files import MockFileFactoryMimeType

# (model_name, provider_name) — used by the litellm adapter prerelease smoke
# tests that exercise basic completion / structured output / tool calling.
PRERELEASE_CHAT_MODELS: list[tuple[str, str]] = [
    ("gpt_5_4_mini", ModelProviderName.openai.value),
    ("claude_4_5_haiku", ModelProviderName.anthropic.value),
    ("claude_sonnet_4_6", ModelProviderName.anthropic.value),
    ("claude_opus_4_7", ModelProviderName.anthropic.value),
    ("gemini_3_flash", ModelProviderName.gemini_api.value),
    ("claude_sonnet_4_6", ModelProviderName.openrouter.value),
    ("gpt_5_4_mini", ModelProviderName.openrouter.value),
    ("llama_3_3_70b", ModelProviderName.groq.value),
    ("qwen_3p6_plus", ModelProviderName.fireworks_ai.value),
    ("minimax_m2_7", ModelProviderName.together_ai.value),
]

# (model_name, provider_name) — used by the embedding prerelease smoke tests
# in both test_ml_embedding_model_list.py and test_litellm_embedding_adapter.py.
# At least one entry per embedding-supporting provider.
PRERELEASE_EMBEDDING_MODELS: list[tuple[str, str]] = [
    ("openai_text_embedding_3_small", ModelProviderName.openai.value),
    ("openai_text_embedding_3_large", ModelProviderName.openai.value),
    ("gemini_embedding_001", ModelProviderName.gemini_api.value),
    ("nomic_text_embedding_v1_5", ModelProviderName.fireworks_ai.value),
    ("baai_bge_large_1_5", ModelProviderName.together_ai.value),
    ("qwen_3_embedding_8b", ModelProviderName.siliconflow_cn.value),
]

# (model_name, provider_name) — used by the doc-extraction prerelease smoke
# tests. One multimodal model per major vendor family.
PRERELEASE_EXTRACTION_MODELS: list[tuple[str, str]] = [
    ("gpt_4o", ModelProviderName.openai.value),
    ("claude_sonnet_4_6", ModelProviderName.anthropic.value),
    ("gemini_3_flash", ModelProviderName.gemini_api.value),
]

# Subset of mime types to exercise in the prerelease extraction smoke test.
# The full paid test sweeps all 13 mime types per model — too slow for prerelease.
# This covers one example per major content category.
PRERELEASE_EXTRACTION_MIME_PROBES: list[tuple[MockFileFactoryMimeType, list[str]]] = [
    (MockFileFactoryMimeType.PDF, ["attention"]),
    (MockFileFactoryMimeType.PNG, ["parrot", "bird", "macaw"]),
    (MockFileFactoryMimeType.MP3, ["ice cube"]),
]

# (provider_name, model_name, thinking_level) — explicit triples for the
# thinking-level reasoning-content prerelease smoke test. Each entry is a
# combo we already know exists in ml_model_list.py and has a meaningful
# reasoning channel; the test verifies the reasoning content channel is
# populated (or absent for "none").
PRERELEASE_THINKING_MODELS: list[tuple[str, str, str]] = [
    (ModelProviderName.openai.value, "gpt_o4_mini_low", "low"),
    (ModelProviderName.anthropic.value, "claude_sonnet_4_6", "medium"),
    (ModelProviderName.anthropic.value, "claude_4_5_haiku", "low"),
    (ModelProviderName.gemini_api.value, "gemini_3_flash", "medium"),
    (ModelProviderName.openrouter.value, "claude_sonnet_4_6", "none"),
]
