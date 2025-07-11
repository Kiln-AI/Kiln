import asyncio
from unittest.mock import patch

import pytest

from kiln_ai.adapters.ml_embedding_model_list import built_in_embedding_models
from kiln_ai.adapters.ml_model_list import built_in_models
from kiln_ai.adapters.remote_config import (
    KilnRemoteConfig,
    deserialize_config,
    dump_builtin_config,
    load_from_url,
    load_remote_models,
    serialize_config,
)


def test_round_trip(tmp_path):
    path = tmp_path / "models.json"
    serialize_config(built_in_models, built_in_embedding_models, path)
    loaded = deserialize_config(path)
    assert [m.model_dump(mode="json") for m in loaded.model_list] == [
        m.model_dump(mode="json") for m in built_in_models
    ]
    assert [m.model_dump(mode="json") for m in loaded.embedding_model_list] == [
        m.model_dump(mode="json") for m in built_in_embedding_models
    ]


def test_load_from_url():
    sample = [built_in_models[0].model_dump(mode="json")]
    sample_embedding = [built_in_embedding_models[0].model_dump(mode="json")]

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"model_list": sample, "embedding_model_list": sample_embedding}

    with patch(
        "kiln_ai.adapters.remote_config.requests.get", return_value=FakeResponse()
    ):
        models = load_from_url("http://example.com/models.json")
    assert [m.model_dump(mode="json") for m in models.model_list] == sample
    assert [
        m.model_dump(mode="json") for m in models.embedding_model_list
    ] == sample_embedding


def test_dump_builtin_config(tmp_path):
    path = tmp_path / "out.json"
    dump_builtin_config(path)
    loaded = deserialize_config(path)
    assert [m.model_dump(mode="json") for m in loaded.model_list] == [
        m.model_dump(mode="json") for m in built_in_models
    ]
    assert [m.model_dump(mode="json") for m in loaded.embedding_model_list] == [
        m.model_dump(mode="json") for m in built_in_embedding_models
    ]


@pytest.mark.asyncio
async def test_load_remote_models_success(monkeypatch):
    monkeypatch.delenv("KILN_SKIP_REMOTE_MODEL_LIST", raising=False)
    original_models = built_in_models.copy()
    original_embedding_models = built_in_embedding_models.copy()
    sample_models = [original_models[0]]
    sample_embedding_models = [original_embedding_models[0]]

    def fake_fetch(url):
        return KilnRemoteConfig(
            model_list=sample_models,
            embedding_model_list=sample_embedding_models,
        )

    monkeypatch.setattr("kiln_ai.adapters.remote_config.load_from_url", fake_fetch)

    load_remote_models("http://example.com/models.json")
    await asyncio.sleep(0.01)
    assert built_in_models == sample_models
    assert built_in_embedding_models == sample_embedding_models


@pytest.mark.asyncio
async def test_load_remote_models_failure(monkeypatch):
    # Ensure the environment variable is not set to skip remote model loading
    monkeypatch.delenv("KILN_SKIP_REMOTE_MODEL_LIST", raising=False)

    original_models = built_in_models.copy()
    original_embedding = built_in_embedding_models.copy()

    def fake_fetch(url):
        raise RuntimeError("fail")

    monkeypatch.setattr("kiln_ai.adapters.remote_config.requests.get", fake_fetch)

    with patch("kiln_ai.adapters.remote_config.logger") as mock_logger:
        load_remote_models("http://example.com/models.json")
        assert built_in_models == original_models
        assert built_in_embedding_models == original_embedding

        # assert that logger.warning was called
        mock_logger.warning.assert_called_once()


def test_deserialize_config_with_extra_keys(tmp_path):
    # Take a valid model and add an extra key, ensure it is ignored and still loads
    import json

    from kiln_ai.adapters.ml_model_list import built_in_models

    model_dict = built_in_models[0].model_dump(mode="json")
    model_dict["extra_key"] = "should be ignored or error"
    model_dict["providers"][0]["extra_key"] = "should be ignored or error"

    embedding_model_dict = built_in_embedding_models[0].model_dump(mode="json")
    embedding_model_dict["extra_key"] = "should be ignored or error"
    embedding_model_dict["providers"][0]["extra_key"] = "should be ignored or error"

    data = {"model_list": [model_dict], "embedding_model_list": [embedding_model_dict]}
    path = tmp_path / "extra.json"
    path.write_text(json.dumps(data))
    # Should NOT raise, and extra key should be ignored
    models = deserialize_config(path)
    assert hasattr(models.model_list[0], "family")
    assert not hasattr(models.model_list[0], "extra_key")
    assert hasattr(models.model_list[0], "providers")
    assert not hasattr(models.model_list[0].providers[0], "extra_key")
    assert hasattr(models.embedding_model_list[0], "family")
    assert not hasattr(models.embedding_model_list[0], "extra_key")
    assert hasattr(models.embedding_model_list[0], "providers")
    assert not hasattr(models.embedding_model_list[0].providers[0], "extra_key")
