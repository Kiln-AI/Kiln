import asyncio
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


def test_backwards_compatibility_with_v0_18(tmp_path):
    """Test that kiln-ai v0.18 (first version with remote config) can parse JSON from current version.

    This ensures our serialization format remains backwards compatible using uv scripts.

    Skipped in CI/CD/VScode (needs UV), so you have to run it from the CLI (fine since it's slow):
    Run from CLI: KILN_TEST_COMPATIBILITY=1 uv run python3 -m pytest libs/core/kiln_ai/adapters/test_remote_config.py::test_backwards_compatibility_with_v0_18 -s -v
    """

    # Skip unless explicitly requested via environment variable
    if not os.environ.get("KILN_TEST_COMPATIBILITY"):
        pytest.skip(
            "Compatibility test skipped. Set KILN_TEST_COMPATIBILITY=1 to run this test."
        )

    import shutil
    import subprocess

    # Check if uv is available
    if not shutil.which("uv"):
        pytest.skip("uv is not available for compatibility test")

    # Create JSON with current version
    current_json_path = tmp_path / "current_models.json"
    serialize_config(built_in_models, current_json_path)

    # Test script using uv inline script metadata to install v0.18
    test_script = f'''# /// script
# dependencies = [
#   "kiln-ai==0.18.0",
#   "pandas",
# ]
# ///
import sys
import json
from pathlib import Path

# Import from v0.18
try:
    from kiln_ai.adapters.remote_config import deserialize_config
    from kiln_ai.adapters.ml_model_list import KilnModel

    # Try to deserialize current JSON with v0.18 code
    models = deserialize_config("{current_json_path}")

    # Basic validation - should have parsed successfully
    assert len(models) > 0
    assert all(isinstance(m, KilnModel) for m in models)

    # Check basic fields exist and have expected types
    for model in models:
        assert hasattr(model, 'family') and isinstance(model.family, str)
        assert hasattr(model, 'name') and isinstance(model.name, str)
        assert hasattr(model, 'friendly_name') and isinstance(model.friendly_name, str)
        assert hasattr(model, 'providers') and isinstance(model.providers, list)

        # Check providers have basic fields
        for provider in model.providers:
            assert hasattr(provider, 'name')

    print("SUCCESS: v0.18 successfully parsed JSON from current version")
    print(f"Parsed {{len(models)}} models")

except Exception as e:
    print(f"ERROR: {{e}}")
    sys.exit(1)
'''

    try:
        # Write the uv script
        script_path = tmp_path / "test_v0_18.py"
        script_path.write_text(test_script)

        # Run the script using uv
        result = subprocess.run(
            ["uv", "run", str(script_path)], capture_output=True, text=True
        )

        # Check if the test passed
        if result.returncode != 0:
            pytest.fail(
                f"v0.18 compatibility test failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
            )

        # Verify success message was printed
        assert (
            "SUCCESS: v0.18 successfully parsed JSON from current version"
            in result.stdout
        )

    except subprocess.CalledProcessError as e:
        # If we can't run uv, skip the test (might be network issues, etc.)
        pytest.skip(f"Could not run uv script for compatibility test: {e}")
    except FileNotFoundError:
        # If uv command not found
        pytest.skip("uv command not found for compatibility test")
