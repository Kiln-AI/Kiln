import os
import tempfile
from unittest.mock import patch

import pytest
from app.desktop.studio_server.webhost import connect_webhost
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient


@pytest.fixture
def temp_studio():
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(d, exist_ok=True)
        with patch("app.desktop.studio_server.webhost.studio_path", lambda: d):
            yield d


@pytest.fixture
def app_with_webhost(temp_studio):
    app = FastAPI()

    @app.get("/api/forced-not-found")
    def forced_not_found():
        raise HTTPException(status_code=404, detail="test missing resource")

    connect_webhost(app)
    return app


def test_not_found_handler_returns_json_for_api_http_exception(app_with_webhost):
    client = TestClient(app_with_webhost)
    response = client.get("/api/forced-not-found")
    assert response.status_code == 404
    assert response.json() == {"detail": "test missing resource"}
    assert response.headers.get("content-type", "").startswith("application/json")


def test_not_found_handler_serves_404_html_for_non_api_paths(temp_studio):
    with open(os.path.join(temp_studio, "404.html"), "w", encoding="utf-8") as f:
        f.write("<html><body>custom not found</body></html>")

    app = FastAPI()
    connect_webhost(app)
    client = TestClient(app)
    response = client.get("/route-that-does-not-exist")
    assert response.status_code == 404
    assert "custom not found" in response.text
