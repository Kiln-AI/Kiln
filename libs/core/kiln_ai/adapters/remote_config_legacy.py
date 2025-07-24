import argparse
import json
import logging
import subprocess
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import List

from kiln_ai.adapters.remote_config import serialize_config

from .ml_model_list import KilnModel, built_in_models

logger = logging.getLogger(__name__)


def serialize_config_v0_18(models: List[KilnModel], path: str | Path) -> None:
    """
    Serialize the models to a JSON file that is compatible with v0.18.

    This function uses uv to install Kiln v0.18 and run a script to filter out
    the models / providers that fail validation in v0.18 - and we write the ones
    that pass to the output file.
    """
    with (
        NamedTemporaryFile(delete=True) as forward_config_serialized,
        NamedTemporaryFile(delete=True) as v0_18_config_temp,
        NamedTemporaryFile(delete=True, suffix=".py") as test_script,
    ):
        # we serialize the latest config to a temporary file
        # we load it with v0.18 using custom code that we write below
        serialize_config(models, forward_config_serialized.name)

        # Test script using uv inline script metadata to install v0.18
        backwards_compatible_v0_18_script = """# /// script
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
    from kiln_ai.adapters.ml_model_list import KilnModel, KilnModelProvider
    from pydantic import ValidationError
    import logging
    
    logger = logging.getLogger(__name__)

    # Try to deserialize current JSON with v0.18 code
    data = json.load(open("{forward_config_serialized}"))

    model_data = data.get("model_list", data if isinstance(data, list) else [])
    models = []
    for model_json in model_data:
        try:
            providers_json = model_json.get("providers", [])
            providers = []
            for provider_json in providers_json:
                try:
                    provider = KilnModelProvider.model_validate(provider_json)
                    providers.append(provider)
                except ValidationError as e:
                    logger.warning("Failed to validate provider %s: %s", provider_json, e)

            model_json["providers"] = []
            model = KilnModel.model_validate(model_json)
            model.providers = providers
            models.append(model)
        except ValidationError as e:
            logger.warning("Failed to validate model %s: %s", model_json, e)

    # Write the models to the file
    Path("{v0_18_config_temp}").write_text(json.dumps({{"model_list": [m.model_dump(mode="json") for m in models]}}, indent=2, sort_keys=True))

    # At this point, we have the JSON file that v0.18 can parse, but we do a sanity check
    # below by trying to deserialize it again - it should not be raising any errors.

    # Try to deserialize the filtered JSON with v0.18 code
    models_deserialized = deserialize_config("{v0_18_config_temp}")

    # Basic validation - should have parsed successfully
    assert len(models_deserialized) > 0
    assert all(isinstance(m, KilnModel) for m in models_deserialized)

    # Check basic fields exist and have expected types
    for model in models_deserialized:
        assert hasattr(model, 'family') and isinstance(model.family, str)
        assert hasattr(model, 'name') and isinstance(model.name, str)
        assert hasattr(model, 'friendly_name') and isinstance(model.friendly_name, str)
        assert hasattr(model, 'providers') and isinstance(model.providers, list)

        # Check providers have basic fields
        for provider in model.providers:
            assert hasattr(provider, 'name')

    print("SUCCESS: v0.18 successfully parsed JSON from current version")

except Exception as e:
    print(f"ERROR: {{e}}")
    sys.exit(1)
""".format(
            forward_config_serialized=forward_config_serialized.name,
            v0_18_config_temp=v0_18_config_temp.name,
        )

        try:
            # Write the uv script
            script_path = Path(test_script.name)
            script_path.write_text(backwards_compatible_v0_18_script)
            script_path.chmod(0o755)  # Add execute permissions

            # Run the script using uv
            result = subprocess.run(
                ["uv", "run", str(script_path)], capture_output=True, text=True
            )

            # Check if the test passed
            if result.returncode != 0:
                raise RuntimeError(
                    f"v0.18 compatible remote config generation failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
                )

            # Verify success message was printed
            assert (
                "SUCCESS: v0.18 successfully parsed JSON from current version"
                in result.stdout
            )

            # config is now ready to be written to the permanent file
            Path(path).write_text(
                json.dumps(
                    {"model_list": [m.model_dump(mode="json") for m in models]},
                    indent=2,
                    sort_keys=True,
                )
            )

        except subprocess.CalledProcessError as e:
            # If we can't run uv, skip the test (might be network issues, etc.)
            raise RuntimeError(f"Could not run uv script for compatibility test: {e}")
        except FileNotFoundError:
            # If uv command not found
            raise RuntimeError("uv command not found for compatibility test")


def dump_builtin_config(path: str | Path) -> None:
    serialize_config_v0_18(built_in_models, path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", help="output path")
    args = parser.parse_args()
    dump_builtin_config(args.path)


if __name__ == "__main__":
    main()
