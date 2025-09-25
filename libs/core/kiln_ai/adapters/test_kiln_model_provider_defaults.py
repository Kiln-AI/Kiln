from kiln_ai.adapters.ml_model_list import (
    KilnModelProvider,
    ModelProviderName,
    StructuredOutputMode,
)


def test_kiln_model_provider_defaults_for_missing_fields():
    data = {"name": ModelProviderName.openai, "model_id": "gpt-4.1"}
    provider = KilnModelProvider.model_validate(data)
    assert provider.supports_structured_output is True
    assert provider.supports_data_gen is True
    assert provider.structured_output_mode == StructuredOutputMode.default
