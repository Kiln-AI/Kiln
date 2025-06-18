import asyncio
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
