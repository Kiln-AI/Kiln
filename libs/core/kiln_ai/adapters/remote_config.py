import argparse
import json
import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List

import requests
from pydantic import ValidationError

from kiln_ai.adapters.ml_embedding_model_list import (
    KilnEmbeddingModel,
    KilnEmbeddingModelProvider,
    built_in_embedding_models,
)
from kiln_ai.adapters.reranker_list import (
    KilnRerankerModel,
    KilnRerankerModelProvider,
    built_in_rerankers,
)
from kiln_ai.datamodel.datamodel_enums import KilnMimeType

from .ml_model_list import KilnModel, KilnModelProvider, built_in_models

logger = logging.getLogger(__name__)


@dataclass
class KilnRemoteConfig:
    model_list: List[KilnModel]
    embedding_model_list: List[KilnEmbeddingModel]
    reranker_model_list: List[KilnRerankerModel]


def serialize_config(
    models: List[KilnModel],
    embedding_models: List[KilnEmbeddingModel],
    reranker_models: List[KilnRerankerModel],
    path: str | Path,
) -> None:
    data = {
        "model_list": [m.model_dump(mode="json") for m in models],
        "embedding_model_list": [m.model_dump(mode="json") for m in embedding_models],
        "reranker_model_list": [m.model_dump(mode="json") for m in reranker_models],
    }
    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True))


def deserialize_config_at_path(
    path: str | Path,
) -> KilnRemoteConfig:
    raw = json.loads(Path(path).read_text())
    return deserialize_config_data(raw)


def deserialize_config_data(
    config_data: Any,
) -> KilnRemoteConfig:
    if not isinstance(config_data, dict):
        raise ValueError(f"Remote config expected dict, got {type(config_data)}")

    model_list = config_data.get("model_list", None)
    if not isinstance(model_list, list):
        raise ValueError(
            f"Remote config expected list of models, got {type(model_list)}"
        )

    embedding_model_data = config_data.get("embedding_model_list", [])
    if not isinstance(embedding_model_data, list):
        raise ValueError(
            f"Remote config expected list of embedding models, got {type(embedding_model_data)}"
        )

    reranker_model_data = config_data.get("reranker_model_list", [])
    if not isinstance(reranker_model_data, list):
        raise ValueError(
            f"Remote config expected list of reranker models, got {type(reranker_model_data)}"
        )

    # We must be careful here, because some of the JSON data may be generated from a forward
    # version of the code that has newer fields / versions of the fields, that may cause
    # the current client this code is running on to fail to validate the item into a KilnModel.
    models = []
    for model_data in model_list:
        # We skip any model that fails validation - the models that the client can support
        # will be pulled from the remote config, but the user will need to update their
        # client to the latest version to see the newer models that break backwards compatibility.
        try:
            providers_list = model_data.get("providers", [])

            providers = []
            for provider_data in providers_list:
                try:
                    # we filter out the mime types that we don't support
                    mime_types = provider_data.get("multimodal_mime_types")
                    if mime_types is not None:
                        provider_data["multimodal_mime_types"] = [
                            mime_type
                            for mime_type in mime_types
                            if mime_type in list(KilnMimeType)
                        ]
                    provider = KilnModelProvider.model_validate(provider_data)
                    providers.append(provider)
                except ValidationError as e:
                    logger.warning(
                        "Failed to validate a model provider from remote config. Upgrade Kiln to use this model. Details %s: %s",
                        provider_data,
                        e,
                    )

            # this ensures the model deserialization won't fail because of a bad provider
            model_data["providers"] = []

            # now we validate the model without its providers
            model = KilnModel.model_validate(model_data)

            # and we attach back the providers that passed our validation
            model.providers = providers
            models.append(model)
        except ValidationError as e:
            logger.warning(
                "Failed to validate a model from remote config. Upgrade Kiln to use this model. Details %s: %s",
                model_data,
                e,
            )

    embedding_models = []
    for embedding_model_data in embedding_model_data:
        try:
            provider_list = embedding_model_data.get("providers", [])
            providers = []
            for provider_data in provider_list:
                try:
                    provider = KilnEmbeddingModelProvider.model_validate(provider_data)
                    providers.append(provider)
                except ValidationError as e:
                    logger.warning(
                        "Failed to validate an embedding model provider from remote config. Upgrade Kiln to use this model. Details %s: %s",
                        provider_data,
                        e,
                    )

            embedding_model_data["providers"] = []
            embedding_model = KilnEmbeddingModel.model_validate(embedding_model_data)
            embedding_model.providers = providers
            embedding_models.append(embedding_model)
        except ValidationError as e:
            logger.warning(
                "Failed to validate an embedding model from remote config. Upgrade Kiln to use this model. Details %s: %s",
                embedding_model_data,
                e,
            )

    reranker_models = []
    for reranker_model_data in reranker_model_data:
        try:
            provider_list = reranker_model_data.get("providers", [])
            providers = []
            for provider_data in provider_list:
                try:
                    provider = KilnRerankerModelProvider.model_validate(provider_data)
                    providers.append(provider)
                except ValidationError as e:
                    logger.warning(
                        "Failed to validate a reranker model provider from remote config. Upgrade Kiln to use this model. Details %s: %s",
                        provider_data,
                        e,
                    )

            reranker_model_data["providers"] = []
            reranker_model = KilnRerankerModel.model_validate(reranker_model_data)
            reranker_model.providers = providers
            reranker_models.append(reranker_model)
        except ValidationError as e:
            logger.warning(
                "Failed to validate a reranker model from remote config. Upgrade Kiln to use this model. Details %s: %s",
                reranker_model_data,
                e,
            )

    return KilnRemoteConfig(
        model_list=models,
        embedding_model_list=embedding_models,
        reranker_model_list=reranker_models,
    )


def load_from_url(url: str) -> KilnRemoteConfig:
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    data = response.json()
    return deserialize_config_data(data)


def dump_builtin_config(path: str | Path) -> None:
    serialize_config(
        models=built_in_models,
        embedding_models=built_in_embedding_models,
        reranker_models=built_in_rerankers,
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
            built_in_rerankers[:] = models.reranker_model_list
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
