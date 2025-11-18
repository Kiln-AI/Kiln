import os
from unittest.mock import patch

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient
from kiln_ai.utils.config import Config
from kiln_ai.utils.model_rate_limiter import (
    get_global_rate_limiter,
    reset_global_rate_limiter,
)

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


def test_provider_limits_new_format(client, temp_home):
    """Test the new format with provider-wide limits."""
    test_rate_limits = {
        "provider_limits": {"openai": 20, "anthropic": 10},
        "model_limits": {},
    }

    response = client.post("/api/rate_limits", json=test_rate_limits)
    assert response.status_code == 200
    assert response.json() == test_rate_limits

    rate_limits_path = os.path.join(Config.settings_dir(), "rate_limits.yaml")
    with open(rate_limits_path, "r") as f:
        saved_rate_limits = yaml.safe_load(f)
    assert saved_rate_limits == test_rate_limits


def test_mixed_provider_and_model_limits(client, temp_home):
    """Test both provider-wide and model-specific limits together."""
    test_rate_limits = {
        "provider_limits": {"openai": 20, "anthropic": 10},
        "model_limits": {
            "openai": {"gpt_5": 5, "gpt_4o": 3},
            "anthropic": {"claude_opus_4_1": 2},
        },
    }

    response = client.post("/api/rate_limits", json=test_rate_limits)
    assert response.status_code == 200
    result = response.json()

    assert result["provider_limits"]["openai"] == 20
    assert result["provider_limits"]["anthropic"] == 10
    assert result["model_limits"]["openai"]["gpt_5"] == 5
    assert result["model_limits"]["openai"]["gpt_4o"] == 3
    assert result["model_limits"]["anthropic"]["claude_opus_4_1"] == 2


def test_read_rate_limits_with_provider_limits(client, temp_home):
    """Test reading rate limits with provider-wide limits from file."""
    rate_limits_path = os.path.join(Config.settings_dir(), "rate_limits.yaml")
    test_rate_limits = {
        "provider_limits": {"openai": 15},
        "model_limits": {"openai": {"gpt_5": 5}},
    }
    with open(rate_limits_path, "w") as f:
        yaml.dump(test_rate_limits, f)

    response = client.get("/api/rate_limits")
    assert response.status_code == 200
    result = response.json()

    assert result["provider_limits"]["openai"] == 15
    assert result["model_limits"]["openai"]["gpt_5"] == 5


def test_backward_compatibility_old_format_api(client, temp_home):
    """Test that API works with old format rate limits in file."""
    rate_limits_path = os.path.join(Config.settings_dir(), "rate_limits.yaml")
    old_format_rate_limits = {
        "openai": {"gpt_5": 10, "gpt_4o": 5},
        "anthropic": {"claude_opus_4_1": 3},
    }
    with open(rate_limits_path, "w") as f:
        yaml.dump(old_format_rate_limits, f)

    response = client.get("/api/rate_limits")
    assert response.status_code == 200
    result = response.json()
    assert result == old_format_rate_limits


def test_update_to_new_format(client, temp_home):
    """Test updating from old format to new format."""
    rate_limits_path = os.path.join(Config.settings_dir(), "rate_limits.yaml")
    old_format_rate_limits = {"openai": {"gpt_5": 10}}
    with open(rate_limits_path, "w") as f:
        yaml.dump(old_format_rate_limits, f)

    new_format_rate_limits = {
        "provider_limits": {"openai": 20},
        "model_limits": {"openai": {"gpt_5": 5}},
    }

    response = client.post("/api/rate_limits", json=new_format_rate_limits)
    assert response.status_code == 200

    with open(rate_limits_path, "r") as f:
        saved_rate_limits = yaml.safe_load(f)
    assert saved_rate_limits == new_format_rate_limits


def test_empty_provider_limits(client, temp_home):
    """Test with empty provider limits but with model limits."""
    test_rate_limits = {
        "provider_limits": {},
        "model_limits": {"openai": {"gpt_5": 10}},
    }

    response = client.post("/api/rate_limits", json=test_rate_limits)
    assert response.status_code == 200
    assert response.json() == test_rate_limits


def test_provider_limits_roundtrip(client, temp_home):
    """Test full roundtrip with provider and model limits."""
    test_rate_limits = {
        "provider_limits": {"openai": 25, "anthropic": 15, "gemini_api": 10},
        "model_limits": {
            "openai": {"gpt_5": 5, "gpt_4o": 8},
            "anthropic": {"claude_opus_4_1": 3},
        },
    }

    post_response = client.post("/api/rate_limits", json=test_rate_limits)
    assert post_response.status_code == 200

    get_response = client.get("/api/rate_limits")
    assert get_response.status_code == 200
    assert get_response.json() == test_rate_limits


def test_update_rate_limits_reloads_global_limiter(client, temp_home):
    """Test that updating rate limits via API reloads the global rate limiter."""
    reset_global_rate_limiter()
    limiter = get_global_rate_limiter()

    initial_limits = {
        "provider_limits": {"openai": 5},
        "model_limits": {"openai": {"gpt_5": 10}},
    }
    client.post("/api/rate_limits", json=initial_limits)

    assert limiter.get_provider_limit("openai") == 5
    assert limiter.get_limit("openai", "gpt_5") == 10

    updated_limits = {
        "provider_limits": {"openai": 15},
        "model_limits": {"openai": {"gpt_5": 20}},
    }
    client.post("/api/rate_limits", json=updated_limits)

    assert limiter.get_provider_limit("openai") == 15
    assert limiter.get_limit("openai", "gpt_5") == 20

    reset_global_rate_limiter()
