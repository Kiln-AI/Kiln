import asyncio
import json
import logging
import os
from unittest.mock import patch

import pytest

from kiln_ai.adapters.ml_model_list import built_in_models
from kiln_ai.adapters.remote_config import (
    deserialize_config,
    dump_builtin_config,
    load_from_url,
    load_remote_models,
    serialize_config,
)


def test_round_trip(tmp_path):
    path = tmp_path / "models.json"
    serialize_config(built_in_models, path)
    loaded = deserialize_config(path)
    assert [m.model_dump(mode="json") for m in loaded] == [
        m.model_dump(mode="json") for m in built_in_models
    ]


def test_load_from_url():
    sample = [built_in_models[0].model_dump(mode="json")]

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"model_list": sample}

    with patch(
        "kiln_ai.adapters.remote_config.requests.get", return_value=FakeResponse()
    ):
        models = load_from_url("http://example.com/models.json")
    assert [m.model_dump(mode="json") for m in models] == sample


def test_dump_builtin_config(tmp_path):
    path = tmp_path / "out.json"
    dump_builtin_config(path)
    loaded = deserialize_config(path)
    assert [m.model_dump(mode="json") for m in loaded] == [
        m.model_dump(mode="json") for m in built_in_models
    ]


@pytest.mark.asyncio
async def test_load_remote_models_success(monkeypatch):
    del os.environ["KILN_SKIP_REMOTE_MODEL_LIST"]
    original = built_in_models.copy()
    sample_models = [built_in_models[0]]

    def fake_fetch(url):
        return sample_models

    monkeypatch.setattr("kiln_ai.adapters.remote_config.load_from_url", fake_fetch)

    load_remote_models("http://example.com/models.json")
    await asyncio.sleep(0.01)
    assert built_in_models == sample_models
    built_in_models[:] = original


@pytest.mark.asyncio
async def test_load_remote_models_failure(monkeypatch):
    original = built_in_models.copy()

    def fake_fetch(url):
        raise RuntimeError("fail")

    monkeypatch.setattr("kiln_ai.adapters.remote_config.load_from_url", fake_fetch)

    load_remote_models("http://example.com/models.json")
    await asyncio.sleep(0.01)
    assert built_in_models == original


def test_deserialize_config_with_extra_keys(tmp_path):
    # Take a valid model and add an extra key, ensure it is ignored and still loads
    import json

    from kiln_ai.adapters.ml_model_list import built_in_models

    model_dict = built_in_models[0].model_dump(mode="json")
    model_dict["extra_key"] = "should be ignored or error"
    model_dict["providers"][0]["extra_key"] = "should be ignored or error"
    data = {"model_list": [model_dict]}
    path = tmp_path / "extra.json"
    path.write_text(json.dumps(data))
    # Should NOT raise, and extra key should be ignored
    models = deserialize_config(path)
    assert hasattr(models[0], "family")
    assert not hasattr(models[0], "extra_key")
    assert hasattr(models[0], "providers")
    assert not hasattr(models[0].providers[0], "extra_key")


def test_deserialize_config_with_invalid_models(tmp_path, caplog):
    """Test comprehensive handling of invalid models and providers during deserialization."""

    # Create a fully valid model as baseline
    valid_model = built_in_models[0].model_dump(mode="json")

    # Case 1: Invalid model - missing required field 'family'
    invalid_model_missing_family = built_in_models[0].model_dump(mode="json")
    del invalid_model_missing_family["family"]

    # Case 2: Invalid model - invalid data type for required field
    invalid_model_wrong_type = built_in_models[0].model_dump(mode="json")
    invalid_model_wrong_type["name"] = None  # name should be a string, not None

    # Case 3: Invalid model - completely malformed
    invalid_model_malformed = {"not_a_valid_model": "at_all"}

    # Case 4: Valid model with one invalid provider (should keep model, skip invalid provider)
    valid_model_invalid_provider = built_in_models[0].model_dump(mode="json")
    valid_model_invalid_provider["name"] = "test_model_invalid_provider"  # Unique name
    valid_model_invalid_provider["providers"][0]["name"] = "unknown-provider-123"

    # Case 5: Valid model with mixed valid/invalid providers (should keep model and valid providers)
    valid_model_mixed_providers = built_in_models[0].model_dump(mode="json")
    valid_model_mixed_providers["name"] = "test_model_mixed_providers"  # Unique name
    # Add a second provider that's valid
    valid_provider = valid_model_mixed_providers["providers"][0].copy()
    valid_provider["name"] = "azure_openai"
    # Make first provider invalid
    valid_model_mixed_providers["providers"][0]["name"] = "invalid-provider-1"
    # Add invalid provider with missing required field
    invalid_provider = valid_model_mixed_providers["providers"][0].copy()
    del invalid_provider["name"]
    # Add another invalid provider with wrong type
    invalid_provider_2 = valid_model_mixed_providers["providers"][0].copy()
    invalid_provider_2["supports_structured_output"] = "not_a_boolean"

    valid_model_mixed_providers["providers"] = [
        valid_model_mixed_providers["providers"][0],  # invalid name
        valid_provider,  # valid
        invalid_provider,  # missing name
        invalid_provider_2,  # wrong type
    ]

    # Case 6: Valid model with all invalid providers (should keep model with empty providers)
    valid_model_all_invalid_providers = built_in_models[0].model_dump(mode="json")
    valid_model_all_invalid_providers["name"] = (
        "test_model_all_invalid_providers"  # Unique name
    )
    valid_model_all_invalid_providers["providers"][0]["name"] = "unknown-provider-456"
    if len(valid_model_all_invalid_providers["providers"]) > 1:
        valid_model_all_invalid_providers["providers"][1]["name"] = (
            "another-unknown-provider"
        )
    if len(valid_model_all_invalid_providers["providers"]) > 2:
        valid_model_all_invalid_providers["providers"][2]["name"] = (
            "yet-another-unknown-provider"
        )

    data = {
        "model_list": [
            valid_model,  # Should be kept
            invalid_model_missing_family,  # Should be skipped
            invalid_model_wrong_type,  # Should be skipped
            invalid_model_malformed,  # Should be skipped
            valid_model_invalid_provider,  # Should be kept with empty providers
            valid_model_mixed_providers,  # Should be kept with 1 valid provider
            valid_model_all_invalid_providers,  # Should be kept with empty providers
        ]
    }
    path = tmp_path / "mixed_models.json"
    path.write_text(json.dumps(data))

    # Enable logging to capture warnings
    with caplog.at_level(logging.WARNING):
        models = deserialize_config(path)

    # Should have 4 valid models (original + 3 with provider issues but valid model structure)
    assert len(models) == 4

    # Check the first model is fully intact
    assert models[0].name == built_in_models[0].name
    assert models[0].family == built_in_models[0].family
    assert len(models[0].providers) == 3  # built_in_models[0] has 3 providers

    # Check model with invalid provider has remaining valid providers
    model_with_invalid_provider = next(
        m for m in models if m.name == valid_model_invalid_provider["name"]
    )
    # Should keep the valid providers from the original model (openrouter, azure_openai)
    assert len(model_with_invalid_provider.providers) == 2
    provider_names = {p.name.value for p in model_with_invalid_provider.providers}
    assert provider_names == {"openrouter", "azure_openai"}

    # Check model with mixed providers has only the valid one
    model_with_mixed_providers = next(
        m for m in models if m.name == valid_model_mixed_providers["name"]
    )
    assert len(model_with_mixed_providers.providers) == 1
    assert model_with_mixed_providers.providers[0].name.value == "azure_openai"

    # Check model with all invalid providers has empty providers
    model_with_all_invalid_providers = next(
        m for m in models if m.name == valid_model_all_invalid_providers["name"]
    )
    assert len(model_with_all_invalid_providers.providers) == 0

    # Check warning logs
    warning_logs = [
        record for record in caplog.records if record.levelno == logging.WARNING
    ]

    # Should have warnings for:
    # - 3 invalid models (missing family, wrong type, malformed)
    # - 1 invalid provider in case 4 (unknown-provider-123)
    # - 3 invalid providers in case 5 (invalid-provider-1, missing name, wrong type boolean)
    # - 3 invalid providers in case 6 (unknown-provider-456, another-unknown-provider, yet-another-unknown-provider)
    assert len(warning_logs) >= 10

    # Check that warning messages contain expected content
    model_warnings = [
        log for log in warning_logs if "Failed to validate model" in log.message
    ]
    provider_warnings = [
        log for log in warning_logs if "Failed to validate provider" in log.message
    ]

    assert len(model_warnings) == 3  # 3 completely invalid models
    assert (
        len(provider_warnings) == 7
    )  # Exactly 7 invalid providers across different models


def test_deserialize_config_empty_provider_list(tmp_path):
    """Test that models with empty provider lists are handled correctly."""
    model_with_empty_providers = built_in_models[0].model_dump(mode="json")
    model_with_empty_providers["providers"] = []

    data = {"model_list": [model_with_empty_providers]}
    path = tmp_path / "empty_providers.json"
    path.write_text(json.dumps(data))

    models = deserialize_config(path)
    assert len(models) == 1
    assert len(models[0].providers) == 0


def test_deserialize_config_missing_provider_field(tmp_path, caplog):
    """Test that models missing the providers field are handled correctly."""
    model_without_providers = built_in_models[0].model_dump(mode="json")
    del model_without_providers["providers"]

    data = {"model_list": [model_without_providers]}
    path = tmp_path / "no_providers.json"
    path.write_text(json.dumps(data))

    with caplog.at_level(logging.WARNING):
        models = deserialize_config(path)

    # Model should be kept with empty providers (deserialize_config handles missing providers gracefully)
    assert len(models) == 1
    assert len(models[0].providers) == 0
    assert models[0].name == built_in_models[0].name

    # Should not have any warnings since the function handles missing providers gracefully
    warning_logs = [
        record for record in caplog.records if record.levelno == logging.WARNING
    ]
    assert len(warning_logs) == 0


def test_deserialize_config_provider_with_extra_fields(tmp_path):
    """Test that providers with extra unknown fields are handled gracefully."""
    model_with_extra_provider_fields = built_in_models[0].model_dump(mode="json")
    model_with_extra_provider_fields["providers"][0]["unknown_field"] = (
        "should_be_ignored"
    )
    model_with_extra_provider_fields["providers"][0]["another_extra"] = {
        "nested": "data"
    }

    data = {"model_list": [model_with_extra_provider_fields]}
    path = tmp_path / "extra_provider_fields.json"
    path.write_text(json.dumps(data))

    models = deserialize_config(path)
    assert len(models) == 1
    assert len(models[0].providers) == 3  # built_in_models[0] has 3 providers
    # Extra fields should be ignored, not present in the final object
    assert not hasattr(models[0].providers[0], "unknown_field")
    assert not hasattr(models[0].providers[0], "another_extra")


def test_deserialize_config_model_with_extra_fields(tmp_path):
    """Test that models with extra unknown fields are handled gracefully."""
    model_with_extra_fields = built_in_models[0].model_dump(mode="json")
    model_with_extra_fields["future_field"] = "should_be_ignored"
    model_with_extra_fields["complex_extra"] = {"nested": {"data": [1, 2, 3]}}

    data = {"model_list": [model_with_extra_fields]}
    path = tmp_path / "extra_model_fields.json"
    path.write_text(json.dumps(data))

    models = deserialize_config(path)
    assert len(models) == 1
    assert models[0].name == built_in_models[0].name
    # Extra fields should be ignored, not present in the final object
    assert not hasattr(models[0], "future_field")
    assert not hasattr(models[0], "complex_extra")


def test_deserialize_config_mixed_valid_invalid_providers_single_model(
    tmp_path, caplog
):
    """Test a single model with a mix of valid and invalid providers in detail."""
    model = built_in_models[0].model_dump(mode="json")

    # Create a mix of provider scenarios
    valid_provider_1 = model["providers"][0].copy()
    valid_provider_1["name"] = "openai"

    valid_provider_2 = model["providers"][0].copy()
    valid_provider_2["name"] = "azure_openai"

    invalid_provider_unknown_name = model["providers"][0].copy()
    invalid_provider_unknown_name["name"] = "nonexistent_provider"

    invalid_provider_missing_name = model["providers"][0].copy()
    del invalid_provider_missing_name["name"]

    invalid_provider_wrong_type = model["providers"][0].copy()
    invalid_provider_wrong_type["supports_structured_output"] = "not_a_boolean"

    model["providers"] = [
        valid_provider_1,
        invalid_provider_unknown_name,
        valid_provider_2,
        invalid_provider_missing_name,
        invalid_provider_wrong_type,
    ]

    data = {"model_list": [model]}
    path = tmp_path / "mixed_providers_single.json"
    path.write_text(json.dumps(data))

    with caplog.at_level(logging.WARNING):
        models = deserialize_config(path)

    # Should have 1 model with 2 valid providers
    assert len(models) == 1
    assert len(models[0].providers) == 2
    assert models[0].providers[0].name.value == "openai"
    assert models[0].providers[1].name.value == "azure_openai"

    # Should have logged 3 provider validation warnings
    provider_warnings = [
        log
        for log in caplog.records
        if log.levelno == logging.WARNING
        and "Failed to validate provider" in log.message
    ]
    assert len(provider_warnings) == 3


def test_deserialize_config_empty_json_structures(tmp_path):
    """Test various empty JSON structures."""
    # Test empty model_list
    data = {"model_list": []}
    path = tmp_path / "empty_model_list.json"
    path.write_text(json.dumps(data))
    models = deserialize_config(path)
    assert len(models) == 0

    # Test empty object with no model_list key
    path = tmp_path / "empty_object.json"
    path.write_text(json.dumps({}))
    models = deserialize_config(path)
    assert len(models) == 0
