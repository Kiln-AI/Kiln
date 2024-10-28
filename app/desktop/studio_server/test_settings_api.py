import os
from unittest.mock import patch

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient
from kiln_ai.utils.config import Config

from app.desktop.studio_server.settings_api import connect_settings


@pytest.fixture
def temp_home(tmp_path):
    with patch.object(os.path, "expanduser", return_value=str(tmp_path)):
        yield tmp_path


@pytest.fixture
def app():
    app = FastAPI()
    connect_settings(app)
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


def test_load_settings_empty(temp_home):
    assert Config.shared().load_settings() == {}


def test_load_settings_existing(temp_home):
    settings_file = Config.settings_path()
    os.makedirs(os.path.dirname(settings_file), exist_ok=True)
    test_settings = {"key": "value"}
    with open(settings_file, "w") as f:
        yaml.dump(test_settings, f)

    assert Config.shared().load_settings() == test_settings


def test_update_settings(client, temp_home):
    new_settings = {"test_key": "test_value", "test_key2": "test_value2"}
    response = client.post("/api/settings", json=new_settings)
    assert response.status_code == 200
    assert response.json() == new_settings

    # Verify the settings were actually updated
    with open(Config.settings_path(), "r") as f:
        saved_settings = yaml.safe_load(f)
    assert saved_settings == new_settings


def test_read_settings(client, temp_home):
    test_settings = {"key1": "value1", "key2": 42}
    Config.shared().update_settings(test_settings)

    response = client.get("/api/settings")
    assert response.status_code == 200
    assert response.json() == test_settings


def test_read_item(client, temp_home):
    response = client.get("/api/settings/setting1")
    assert response.status_code == 200
    assert response.json() == {"setting1": None}
    Config.shared().update_settings({"setting1": "value1"})
    response = client.get("/api/settings/setting1")
    assert response.status_code == 200
    assert response.json() == {"setting1": "value1"}


def test_clear_setting(client, temp_home):
    # First, set a value
    initial_settings = {"test_key": "test_value"}
    Config.shared().update_settings(initial_settings)

    # Verify the setting was set
    response = client.get("/api/settings/test_key")
    assert response.status_code == 200
    assert response.json() == {"test_key": "test_value"}

    # Now, clear the setting by posting a null value
    clear_settings = {"test_key": None}
    response = client.post("/api/settings", json=clear_settings)
    assert response.status_code == 200
    assert response.json() == {}

    # Verify the setting was cleared
    response = client.get("/api/settings/test_key")
    assert response.status_code == 200
    assert response.json() == {"test_key": None}

    # Check the full settings to ensure the key was removed
    response = client.get("/api/settings")
    assert response.status_code == 200
    assert "test_key" not in response.json()


@pytest.fixture
def mock_config(monkeypatch):
    mock_settings = {
        "public_setting": "visible",
        "sensitive_setting": "secret",
    }

    class MockConfig:
        @staticmethod
        def shared():
            return MockConfig()

        def settings(self, hide_sensitive=False):
            if hide_sensitive:
                return {
                    k: "[hidden]" if k == "sensitive_setting" else v
                    for k, v in mock_settings.items()
                }
            return mock_settings

        def update_settings(self, new_settings):
            mock_settings.update(new_settings)

    monkeypatch.setattr(Config, "shared", MockConfig.shared)
    return MockConfig()


# Confirm secrets are hidden
def test_settings_endpoints(client, mock_config):
    # Test GET /settings
    response = client.get("/api/settings")
    assert response.status_code == 200
    assert response.json() == {
        "public_setting": "visible",
        "sensitive_setting": "[hidden]",
    }

    # Test POST /settings
    new_settings = {"public_setting": "new_value", "sensitive_setting": "new_secret"}
    response = client.post("/api/settings", json=new_settings)
    assert response.status_code == 200
    assert response.json() == {
        "public_setting": "new_value",
        "sensitive_setting": "[hidden]",
    }

    # Test GET /settings/{item_id}
    response = client.get("/api/settings/public_setting")
    assert response.status_code == 200
    assert response.json() == {"public_setting": "new_value"}

    response = client.get("/api/settings/sensitive_setting")
    assert response.status_code == 200
    assert response.json() == {"sensitive_setting": "[hidden]"}
