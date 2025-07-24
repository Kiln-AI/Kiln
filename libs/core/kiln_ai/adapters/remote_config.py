import argparse
import json
import logging
import os
import threading
from pathlib import Path
from typing import List

import requests
from pydantic import ValidationError

from .ml_model_list import KilnModel, KilnModelProvider, built_in_models

logger = logging.getLogger(__name__)


def serialize_config(models: List[KilnModel], path: str | Path) -> None:
    data = {"model_list": [m.model_dump(mode="json") for m in models]}
    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True))


def deserialize_config(path: str | Path) -> List[KilnModel]:
    raw = json.loads(Path(path).read_text())
    if isinstance(raw, list):
        model_data = raw
    else:
        model_data = raw.get("model_list", [])

    # We must be careful here, because some of the JSON data may be generated from a forward
    # version of the code that has newer fields / versions of the fields, that may cause
    # the current client this code is running on to fail to validate the item into a KilnModel.
    models = []
    for model_json in model_data:
        # We skip any model that fails validation - the models that the client can support
        # will be pulled from the remote config, but the user will need to update their
        # client to the latest version to see the newer models that break backwards compatibility.
        try:
            providers_json = model_json.get("providers", [])

            providers = []
            for provider_json in providers_json:
                try:
                    provider = KilnModelProvider.model_validate(provider_json)
                    providers.append(provider)
                except ValidationError as e:
                    logger.warning(
                        "Failed to validate provider %s: %s", provider_json, e
                    )

            # this ensures the model deserialization won't fail because of a provider
            model_json["providers"] = []

            # now we validate the model without its providers
            model = KilnModel.model_validate(model_json)

            # and we attach back the providers that passed our validation
            model.providers = providers
            models.append(model)
        except ValidationError as e:
            logger.warning("Failed to validate model %s: %s", model_json, e)
    return models


def load_from_url(url: str) -> List[KilnModel]:
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    data = response.json()
    if isinstance(data, list):
        model_data = data
    else:
        model_data = data.get("model_list", [])
    return [KilnModel.model_validate(item) for item in model_data]


def dump_builtin_config(path: str | Path) -> None:
    serialize_config(built_in_models, path)


def load_remote_models(url: str) -> None:
    if os.environ.get("KILN_SKIP_REMOTE_MODEL_LIST") == "true":
        return

    def fetch_and_replace() -> None:
        try:
            models = load_from_url(url)
            built_in_models[:] = models
        except Exception as exc:
            # Do not crash startup, but surface the issue
            logger.warning("Failed to fetch remote model list from %s: %s", url, exc)

    thread = threading.Thread(target=fetch_and_replace, daemon=True)
    thread.start()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", help="output path")
    args = parser.parse_args()
    dump_builtin_config(args.path)


if __name__ == "__main__":
    main()
