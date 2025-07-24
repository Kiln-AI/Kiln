import os
import shutil
import subprocess

import pytest

from kiln_ai.adapters.ml_model_list import built_in_models
from kiln_ai.adapters.remote_config import deserialize_config
from kiln_ai.adapters.remote_config_legacy import serialize_config_v0_18


def test_deserialize_config_v0_18_format(tmp_path):
    """Test that the v0.18 format serialization works and can be deserialized.

    This test uses serialize_config_v0_18 which runs uv to install and test v0.18 compatibility.
    Skip unless explicitly requested via environment variable.

    Run from CLI: KILN_TEST_COMPATIBILITY=1 uv run python3 -m pytest libs/core/kiln_ai/adapters/test_remote_config_legacy.py::test_deserialize_config_v0_18_format -s -v
    """
    # Skip unless explicitly requested via environment variable
    if not os.environ.get("KILN_TEST_COMPATIBILITY"):
        pytest.skip(
            "V0.18 compatibility test skipped. Set KILN_TEST_COMPATIBILITY=1 to run this test."
        )

    # Check if uv is available
    if not shutil.which("uv"):
        pytest.skip("uv is not available for v0.18 compatibility test")

    v0_18_path = tmp_path / "v0_18_list.json"
    serialize_config_v0_18(built_in_models, v0_18_path)

    # Verify the file was created and can be deserialized
    assert v0_18_path.exists()
    models = deserialize_config(v0_18_path)

    # Basic validation that deserialization worked
    assert len(models) > 0
    assert all(isinstance(m, type(built_in_models[0])) for m in models)

    # Check that we have some of the expected models
    model_names = {m.name for m in models}
    built_in_names = {m.name for m in built_in_models}
    assert model_names.issubset(built_in_names), (
        f"Unexpected models: {model_names - built_in_names}"
    )


def test_backwards_compatibility_with_v0_18(tmp_path):
    """Test that kiln-ai v0.18 (first version with remote config) can parse JSON from current version.

    This ensures our serialization format remains backwards compatible using uv scripts.

    Skipped in CI/CD/VScode (needs UV), so you have to run it from the CLI (fine since it's slow):
    Run from CLI: KILN_TEST_COMPATIBILITY=1 uv run python3 -m pytest libs/core/kiln_ai/adapters/test_remote_config_legacy.py::test_backwards_compatibility_with_v0_18 -s -v
    """

    # Skip unless explicitly requested via environment variable
    if not os.environ.get("KILN_TEST_COMPATIBILITY"):
        pytest.skip(
            "Compatibility test skipped. Set KILN_TEST_COMPATIBILITY=1 to run this test."
        )

    # Check if uv is available
    if not shutil.which("uv"):
        pytest.skip("uv is not available for compatibility test")

    # Create JSON with current version
    current_json_path = tmp_path / "current_models.json"
    serialize_config_v0_18(built_in_models, current_json_path)

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

        print(current_json_path)

    except subprocess.CalledProcessError as e:
        # If we can't run uv, skip the test (might be network issues, etc.)
        pytest.skip(f"Could not run uv script for compatibility test: {e}")
    except FileNotFoundError:
        # If uv command not found
        pytest.skip("uv command not found for compatibility test")
