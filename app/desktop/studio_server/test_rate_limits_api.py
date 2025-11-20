import os
from unittest.mock import patch

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient
from kiln_ai.utils.config import Config
from kiln_ai.utils.model_rate_limiter import ModelRateLimiter

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


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Reset the shared ModelRateLimiter instance between tests."""
    ModelRateLimiter._shared_instance = None
    yield
    ModelRateLimiter._shared_instance = None


def test_read_rate_limits_empty(client, temp_home):
    response = client.get("/api/rate_limits")
    assert response.status_code == 200
    # Empty file returns empty rate limits model
    result = response.json()
    assert result["provider_limits"] == {}
    assert result["model_limits"] == {}


def test_read_rate_limits_existing(client, temp_home):
    rate_limits_path = os.path.join(Config.settings_dir(), "rate_limits.yaml")
    test_rate_limits = {
        "provider_limits": {},
        "model_limits": {"openai": {"gpt_5": 10, "gpt_4o": 5}},
    }
    with open(rate_limits_path, "w") as f:
        yaml.dump(test_rate_limits, f)

    response = client.get("/api/rate_limits")
    assert response.status_code == 200
    assert response.json() == test_rate_limits


def test_update_rate_limits(client, temp_home):
    new_rate_limits = {
        "provider_limits": {},
        "model_limits": {
            "openai": {"gpt_5": 10, "gpt_4o": 5},
            "anthropic": {"claude_opus_4_1": 3},
        },
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
    initial_rate_limits = {"model_limits": {"openai": {"gpt_5": 10}}}
    with open(rate_limits_path, "w") as f:
        yaml.dump(initial_rate_limits, f)

    new_rate_limits = {
        "provider_limits": {},
        "model_limits": {"anthropic": {"claude_opus_4_1": 5}},
    }
    response = client.post("/api/rate_limits", json=new_rate_limits)
    assert response.status_code == 200
    assert response.json() == new_rate_limits

    with open(rate_limits_path, "r") as f:
        saved_rate_limits = yaml.safe_load(f)
    assert saved_rate_limits == new_rate_limits


def test_update_rate_limits_empty_clears_file(client, temp_home):
    rate_limits_path = os.path.join(Config.settings_dir(), "rate_limits.yaml")
    initial_rate_limits = {"model_limits": {"openai": {"gpt_5": 10}}}
    with open(rate_limits_path, "w") as f:
        yaml.dump(initial_rate_limits, f)

    empty_limits = {"provider_limits": {}, "model_limits": {}}
    response = client.post("/api/rate_limits", json=empty_limits)
    assert response.status_code == 200
    assert response.json() == empty_limits

    with open(rate_limits_path, "r") as f:
        saved_rate_limits = yaml.safe_load(f)
    assert saved_rate_limits == empty_limits


def test_rate_limits_roundtrip(client, temp_home):
    test_rate_limits = {
        "provider_limits": {},
        "model_limits": {
            "openai": {"gpt_5": 10, "gpt_4o": 5},
            "anthropic": {"claude_opus_4_1": 3},
            "gemini_api": {"gemini_2_0_flash_exp": 8},
        },
    }

    post_response = client.post("/api/rate_limits", json=test_rate_limits)
    assert post_response.status_code == 200

    get_response = client.get("/api/rate_limits")
    assert get_response.status_code == 200
    assert get_response.json() == test_rate_limits


def test_rate_limits_nested_structure(client, temp_home):
    test_rate_limits = {
        "provider_limits": {},
        "model_limits": {
            "openai": {
                "gpt_5": 10,
                "gpt_5_1": 8,
                "gpt_4o": 5,
            }
        },
    }

    response = client.post("/api/rate_limits", json=test_rate_limits)
    assert response.status_code == 200
    assert response.json() == test_rate_limits

    get_response = client.get("/api/rate_limits")
    assert get_response.status_code == 200
    assert get_response.json()["model_limits"]["openai"]["gpt_5"] == 10
    assert get_response.json()["model_limits"]["openai"]["gpt_5_1"] == 8
    assert get_response.json()["model_limits"]["openai"]["gpt_4o"] == 5


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


def test_validation_invalid_rate_limits(client, temp_home):
    """Test that invalid rate limits are rejected with proper validation."""
    invalid_limits = {
        "provider_limits": {"openai": "not_a_number"},
        "model_limits": {},
    }
    response = client.post("/api/rate_limits", json=invalid_limits)
    assert response.status_code == 422  # FastAPI validation error


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


def test_update_rate_limits_reloads_shared_limiter(client, temp_home):
    """Test that updating rate limits via API reloads the shared rate limiter."""
    limiter = ModelRateLimiter.shared()

    initial_limits = {
        "provider_limits": {"openai": 5},
        "model_limits": {"openai": {"gpt_5": 10}},
    }
    client.post("/api/rate_limits", json=initial_limits)

    assert limiter._get_provider_limit("openai") == 5
    assert limiter._get_model_limit("openai", "gpt_5") == 10

    updated_limits = {
        "provider_limits": {"openai": 15},
        "model_limits": {"openai": {"gpt_5": 20}},
    }
    client.post("/api/rate_limits", json=updated_limits)

    assert limiter._get_provider_limit("openai") == 15
    assert limiter._get_model_limit("openai", "gpt_5") == 20


def test_read_rate_limits_handles_exception(client, temp_home):
    """Test that read_rate_limits handles exceptions properly."""
    with patch(
        "app.desktop.studio_server.rate_limits_api.ModelRateLimiter.load_rate_limits",
        side_effect=Exception("Unexpected error"),
    ):
        response = client.get("/api/rate_limits")
        assert response.status_code == 500
        assert "Unexpected error" in response.json()["detail"]


def test_update_rate_limits_handles_exception(client, temp_home):
    """Test that update_rate_limits handles exceptions properly."""
    test_limits = {
        "provider_limits": {"openai": 10},
        "model_limits": {},
    }

    with patch(
        "app.desktop.studio_server.rate_limits_api.ModelRateLimiter.shared"
    ) as mock_shared:
        mock_limiter = mock_shared.return_value
        mock_limiter.update_rate_limits.side_effect = Exception("Update failed")

        response = client.post("/api/rate_limits", json=test_limits)
        assert response.status_code == 500
        assert "Update failed" in response.json()["detail"]
