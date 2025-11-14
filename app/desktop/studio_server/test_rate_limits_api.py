import os
from unittest.mock import patch

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient
from kiln_ai.utils.config import Config

from app.desktop.studio_server.rate_limits_api import connect_rate_limits


@pytest.fixture
def temp_home(tmp_path):
    with patch.object(os.path, "expanduser", return_value=str(tmp_path)):
        yield tmp_path


@pytest.fixture
def app():
    app = FastAPI()
    connect_rate_limits(app)
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


def test_read_rate_limits_empty(client, temp_home):
    response = client.get("/api/rate_limits")
    assert response.status_code == 200
    assert response.json() == {}


def test_read_rate_limits_existing(client, temp_home):
    rate_limits_path = os.path.join(Config.settings_dir(), "rate_limits.yaml")
    test_rate_limits = {"openai": {"gpt_5": 10, "gpt_4o": 5}}
    with open(rate_limits_path, "w") as f:
        yaml.dump(test_rate_limits, f)

    response = client.get("/api/rate_limits")
    assert response.status_code == 200
    assert response.json() == test_rate_limits


def test_update_rate_limits(client, temp_home):
    new_rate_limits = {
        "openai": {"gpt_5": 10, "gpt_4o": 5},
        "anthropic": {"claude_opus_4_1": 3},
    }
    response = client.post("/api/rate_limits", json=new_rate_limits)
    assert response.status_code == 200
    assert response.json() == new_rate_limits

    rate_limits_path = os.path.join(Config.settings_dir(), "rate_limits.yaml")
    with open(rate_limits_path, "r") as f:
        saved_rate_limits = yaml.safe_load(f)
    assert saved_rate_limits == new_rate_limits


def test_update_rate_limits_overwrites_existing(client, temp_home):
    rate_limits_path = os.path.join(Config.settings_dir(), "rate_limits.yaml")
    initial_rate_limits = {"openai": {"gpt_5": 10}}
    with open(rate_limits_path, "w") as f:
        yaml.dump(initial_rate_limits, f)

    new_rate_limits = {"anthropic": {"claude_opus_4_1": 5}}
    response = client.post("/api/rate_limits", json=new_rate_limits)
    assert response.status_code == 200
    assert response.json() == new_rate_limits

    with open(rate_limits_path, "r") as f:
        saved_rate_limits = yaml.safe_load(f)
    assert saved_rate_limits == new_rate_limits


def test_update_rate_limits_empty_clears_file(client, temp_home):
    rate_limits_path = os.path.join(Config.settings_dir(), "rate_limits.yaml")
    initial_rate_limits = {"openai": {"gpt_5": 10}}
    with open(rate_limits_path, "w") as f:
        yaml.dump(initial_rate_limits, f)

    response = client.post("/api/rate_limits", json={})
    assert response.status_code == 200
    assert response.json() == {}

    with open(rate_limits_path, "r") as f:
        saved_rate_limits = yaml.safe_load(f)
    assert saved_rate_limits is None or saved_rate_limits == {}


def test_get_all_models_structure(client, temp_home):
    response = client.get("/api/models/all")
    assert response.status_code == 200

    data = response.json()
    assert "normal_models" in data
    assert "embedding_models" in data
    assert "reranker_models" in data

    assert isinstance(data["normal_models"], list)
    assert isinstance(data["embedding_models"], list)
    assert isinstance(data["reranker_models"], list)


def test_get_all_models_returns_models(client, temp_home):
    response = client.get("/api/models/all")
    assert response.status_code == 200

    data = response.json()

    assert len(data["normal_models"]) > 0
    assert len(data["embedding_models"]) > 0
    assert len(data["reranker_models"]) > 0


def test_get_all_models_model_structure(client, temp_home):
    response = client.get("/api/models/all")
    assert response.status_code == 200

    data = response.json()

    for model in data["normal_models"][:5]:
        assert "model_name" in model
        assert "friendly_name" in model
        assert "provider_name" in model
        assert "model_id" in model or model["model_id"] is None

        assert isinstance(model["model_name"], str)
        assert isinstance(model["friendly_name"], str)
        assert isinstance(model["provider_name"], str)

    for model in data["embedding_models"][:5]:
        assert "model_name" in model
        assert "friendly_name" in model
        assert "provider_name" in model
        assert "model_id" in model

        assert isinstance(model["model_name"], str)
        assert isinstance(model["friendly_name"], str)
        assert isinstance(model["provider_name"], str)
        assert isinstance(model["model_id"], str)

    for model in data["reranker_models"][:5]:
        assert "model_name" in model
        assert "friendly_name" in model
        assert "provider_name" in model
        assert "model_id" in model

        assert isinstance(model["model_name"], str)
        assert isinstance(model["friendly_name"], str)
        assert isinstance(model["provider_name"], str)
        assert isinstance(model["model_id"], str)


def test_get_all_models_has_known_models(client, temp_home):
    response = client.get("/api/models/all")
    assert response.status_code == 200

    data = response.json()

    normal_model_names = {model["model_name"] for model in data["normal_models"]}
    assert "gpt_5_1" in normal_model_names or "gpt_5" in normal_model_names

    embedding_model_names = {model["model_name"] for model in data["embedding_models"]}
    assert (
        "openai_text_embedding_3_small" in embedding_model_names
        or "openai_text_embedding_3_large" in embedding_model_names
    )


def test_get_all_models_groups_by_provider(client, temp_home):
    response = client.get("/api/models/all")
    assert response.status_code == 200

    data = response.json()

    openai_normal_models = [
        model for model in data["normal_models"] if model["provider_name"] == "openai"
    ]
    assert len(openai_normal_models) > 0

    openai_embedding_models = [
        model
        for model in data["embedding_models"]
        if model["provider_name"] == "openai"
    ]
    assert len(openai_embedding_models) > 0


def test_rate_limits_roundtrip(client, temp_home):
    test_rate_limits = {
        "openai": {"gpt_5": 10, "gpt_4o": 5},
        "anthropic": {"claude_opus_4_1": 3},
        "gemini_api": {"gemini_2_0_flash_exp": 8},
    }

    post_response = client.post("/api/rate_limits", json=test_rate_limits)
    assert post_response.status_code == 200

    get_response = client.get("/api/rate_limits")
    assert get_response.status_code == 200
    assert get_response.json() == test_rate_limits


def test_rate_limits_nested_structure(client, temp_home):
    test_rate_limits = {
        "openai": {
            "gpt_5": 10,
            "gpt_5_1": 8,
            "gpt_4o": 5,
        }
    }

    response = client.post("/api/rate_limits", json=test_rate_limits)
    assert response.status_code == 200
    assert response.json() == test_rate_limits

    get_response = client.get("/api/rate_limits")
    assert get_response.status_code == 200
    assert get_response.json()["openai"]["gpt_5"] == 10
    assert get_response.json()["openai"]["gpt_5_1"] == 8
    assert get_response.json()["openai"]["gpt_4o"] == 5
