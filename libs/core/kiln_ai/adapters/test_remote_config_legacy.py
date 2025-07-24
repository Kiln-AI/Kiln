import pytest

from kiln_ai.adapters.ml_model_list import built_in_models
from kiln_ai.adapters.remote_config import deserialize_config
from kiln_ai.adapters.remote_config_legacy import serialize_config_v0_18


def test_deserialize_config_v0_18_format(tmp_path):
    """Test that the v0.18 format serialization works and can be deserialized.

    This test uses serialize_config_v0_18 which runs uv to install and test v0.18 compatibility.
    Skip unless explicitly requested via environment variable.

    Run from CLI: KILN_TEST_COMPATIBILITY=1 uv run python3 -m pytest libs/core/kiln_ai/adapters/test_remote_config.py::test_deserialize_config_v0_18_format -s -v
    """
    import os
    import shutil

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
