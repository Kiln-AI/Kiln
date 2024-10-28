import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest
import requests
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.desktop.desktop_server import make_app
from app.desktop.studio_server.webhost import HTMLStaticFiles


@pytest.fixture
def client():
    # a client based on a mock studio path
    with tempfile.TemporaryDirectory() as temp_dir:
        os.makedirs(temp_dir, exist_ok=True)
        with patch(
            "app.desktop.studio_server.webhost.studio_path", new=lambda: temp_dir
        ):
            from app.desktop.studio_server.webhost import studio_path

            assert studio_path() == temp_dir  # Verify the patch is working
            app = make_app()
            client = TestClient(app)
            yield client


def test_ping(client):
    response = client.get("/ping")
    assert response.status_code == 200
    assert response.json() == "pong"


def test_connect_ollama_success(client):
    with patch("requests.get") as mock_get:
        mock_get.return_value.json.return_value = {
            "models": [{"model": "phi3.5:latest"}]
        }
        response = client.post("/api/provider/ollama/connect")
        assert response.status_code == 200
        assert response.json() == {
            "message": "Ollama connected",
            "models": ["phi3.5:latest"],
        }


def test_connect_ollama_connection_error(client):
    with patch("requests.get") as mock_get:
        mock_get.side_effect = requests.exceptions.ConnectionError
        response = client.post("/api/provider/ollama/connect")
        assert response.status_code == 417
        assert response.json() == {
            "message": "Failed to connect. Ensure Ollama app is running."
        }


def test_connect_ollama_general_exception(client):
    with patch("requests.get") as mock_get:
        mock_get.side_effect = Exception("Test exception")
        response = client.post("/api/provider/ollama/connect")
        assert response.status_code == 500
        assert response.json() == {
            "message": "Failed to connect to Ollama: Test exception"
        }


def test_connect_ollama_no_models(client):
    with patch("requests.get") as mock_get:
        mock_get.return_value.json.return_value = {"models": []}
        response = client.post("/api/provider/ollama/connect")
        assert response.status_code == 417
        assert (
            "Ollama is running, but no supported models are installed"
            in response.json()["message"]
        )


@pytest.mark.parametrize(
    "origin",
    [
        "http://localhost",
        "http://localhost:8000",
        "http://127.0.0.1",
        "http://127.0.0.1:3000",
        "https://localhost:8443",
        "https://127.0.0.1:8443",
    ],
)
def test_cors_allowed_origins(client, origin):
    response = client.get("/ping", headers={"Origin": origin})
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin


@pytest.mark.parametrize(
    "origin",
    [
        "http://example.com",
        "https://kiln-ai.com",
        "http://192.168.1.100",
        "http://localhost.com",
        "http://127.0.0.2",
        "http://127.0.0.2.com",
    ],
)
def test_cors_blocked_origins(client, origin):
    response = client.get("/ping", headers={"Origin": origin})
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def create_studio_test_file(relative_path):
    from app.desktop.studio_server.webhost import studio_path

    full_path = os.path.join(studio_path(), relative_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w") as f:
        f.write("<html><body>Test</body></html>")
    return full_path


def test_cors_no_origin(client):
    # Create index.html in the mock studio path
    create_studio_test_file("index.html")

    # Use the client to get the root path
    response = client.get("/")

    # Assert the response
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


class TestHTMLStaticFiles:
    @pytest.fixture
    def html_static_files(self):
        import os
        import tempfile

        self.test_dir = tempfile.mkdtemp()
        with open(os.path.join(self.test_dir, "existing_file"), "w") as f:
            f.write("Test content")
        return HTMLStaticFiles(directory=self.test_dir, html=True)

    @pytest.mark.asyncio
    async def test_get_response_existing_file(self, html_static_files):
        with patch("fastapi.staticfiles.StaticFiles.get_response") as mock_get_response:
            mock_response = MagicMock()
            mock_get_response.return_value = mock_response

            response = await html_static_files.get_response("existing_file", {})

            assert response == mock_response
            mock_get_response.assert_called_once_with("existing_file", {})

    @pytest.mark.asyncio
    async def test_get_response_html_fallback(self, html_static_files):
        with patch("fastapi.staticfiles.StaticFiles.get_response") as mock_get_response:

            def side_effect(path, scope):
                if path.endswith(".html"):
                    return MagicMock()
                raise HTTPException(status_code=404)

            mock_get_response.side_effect = side_effect

            response = await html_static_files.get_response("non_existing_file", {})

            assert response is not None
            assert mock_get_response.call_count == 2
            mock_get_response.assert_any_call("non_existing_file", {})
            mock_get_response.assert_any_call("non_existing_file.html", {})

    @pytest.mark.asyncio
    async def test_get_response_not_found(self, html_static_files):
        with patch("fastapi.staticfiles.StaticFiles.get_response") as mock_get_response:
            mock_get_response.side_effect = HTTPException(status_code=404)

            with pytest.raises(HTTPException):
                await html_static_files.get_response("non_existing_file", {})


@pytest.mark.asyncio
async def test_setup_route(client):
    # Ensure studio_path exists
    create_studio_test_file("index.html")
    create_studio_test_file("path.html")
    create_studio_test_file("nested/index.html")

    # root index.html
    response = client.get("/")
    assert response.status_code == 200
    assert response.text == "<html><body>Test</body></html>"
    # setup.html
    response = client.get("/path")
    assert response.status_code == 200
    assert response.text == "<html><body>Test</body></html>"
    # nested index.html
    response = client.get("/nested")
    assert response.status_code == 200
    assert response.text == "<html><body>Test</body></html>"
    # non existing file

    # expected 404
    with pytest.raises(Exception):
        client.get("/non_existing_file")
    with pytest.raises(Exception):
        client.get("/nested/non_existing_file")
