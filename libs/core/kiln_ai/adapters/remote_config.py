import argparse
import json
import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import List

import requests

from kiln_ai.adapters.ml_embedding_model_list import (
    KilnEmbeddingModel,
    built_in_embedding_models,
)

from .ml_model_list import KilnModel, built_in_models

logger = logging.getLogger(__name__)


@dataclass
class KilnRemoteConfig:
    model_list: List[KilnModel]
    embedding_model_list: List[KilnEmbeddingModel]


def serialize_config(
    models: List[KilnModel],
    embedding_models: List[KilnEmbeddingModel],
    path: str | Path,
) -> None:
    data = {
        "model_list": [m.model_dump(mode="json") for m in models],
        "embedding_model_list": [m.model_dump(mode="json") for m in embedding_models],
    }
    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True))


def deserialize_config(path: str | Path) -> KilnRemoteConfig:
    raw = json.loads(Path(path).read_text())

    model_data = raw.get("model_list", [])
    embedding_model_data = raw.get("embedding_model_list", [])

    return KilnRemoteConfig(
        model_list=[KilnModel.model_validate(item) for item in model_data],
        embedding_model_list=[
            KilnEmbeddingModel.model_validate(item) for item in embedding_model_data
        ],
    )


def load_from_url(url: str) -> KilnRemoteConfig:
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    data = response.json()

    model_data = data.get("model_list", [])
    embedding_model_data = data.get("embedding_model_list", [])

    return KilnRemoteConfig(
        model_list=[KilnModel.model_validate(item) for item in model_data],
        embedding_model_list=[
            KilnEmbeddingModel.model_validate(item) for item in embedding_model_data
        ],
    )


def dump_builtin_config(path: str | Path) -> None:
    serialize_config(
        models=built_in_models,
        embedding_models=built_in_embedding_models,
        path=path,
    )


def load_remote_models(url: str) -> None:
    if os.environ.get("KILN_SKIP_REMOTE_MODEL_LIST") == "true":
        return

    def fetch_and_replace() -> None:
        try:
            models = load_from_url(url)
            built_in_models[:] = models.model_list
            built_in_embedding_models[:] = models.embedding_model_list
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
