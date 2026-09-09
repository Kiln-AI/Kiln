import errno
import os
import tempfile
from unittest.mock import patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from kiln_server.custom_errors import connect_custom_errors

from app.desktop.studio_server.webhost import connect_webhost

WEB_APP_404_BODY = "<html><body>custom not found</body></html>"


@pytest.fixture
def temp_studio():
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(d, exist_ok=True)
        # The compiled web app always ships a 404.html: StaticFiles in html mode
        # will serve it for any miss unless we prevent it on API paths.
        with open(os.path.join(d, "404.html"), "w", encoding="utf-8") as f:
            f.write(WEB_APP_404_BODY)
        with patch("app.desktop.studio_server.webhost.studio_path", lambda: d):
            yield d


@pytest.fixture
def app_with_webhost(temp_studio):
    app = FastAPI()

    @app.get("/api/forced-not-found")
    def forced_not_found():
        raise HTTPException(status_code=404, detail="test missing resource")

    @app.get("/api/get-only")
    def get_only():
        return {"ok": True}

    connect_webhost(app)
    return app


@pytest.fixture
def client(app_with_webhost):
    return TestClient(app_with_webhost)


def assert_json_404(response, message="Not Found"):
    assert response.status_code == 404
    assert response.headers.get("content-type", "").startswith("application/json")
    assert response.json() == {"message": message}


def assert_json_405(response):
    assert response.status_code == 405
    assert response.headers.get("content-type", "").startswith("application/json")


def test_not_found_handler_returns_json_for_api_http_exception(client):
    assert_json_404(client.get("/api/forced-not-found"), "test missing resource")


@pytest.mark.parametrize(
    "path",
    [
        "/api",
        "/api/",
        "/api/some-unmatched-path",
        "/api/nested/unmatched/path",
        "/api/unmatched.html",
    ],
)
def test_unmatched_api_paths_return_json_not_web_app_404(client, path):
    response = client.get(path)
    assert_json_404(response)
    assert WEB_APP_404_BODY not in response.text


def test_api_head_request_returns_json_404(client):
    # HEAD responses carry no body, so the JSON shape can't be asserted here.
    response = client.head("/api/some-unmatched-path")
    assert response.status_code == 404
    assert response.headers.get("content-type", "").startswith("application/json")
    assert response.text == ""


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE", "OPTIONS"])
@pytest.mark.parametrize("path", ["/api/some-unmatched-path", "/api/get-only"])
def test_non_get_method_on_api_path_keeps_405(client, method, path):
    # The web host mount matches every path, so any method the static file
    # server doesn't serve reaches it and gets its 405 (which, unlike a
    # router-generated one, carries no Allow header). All of this predates the
    # JSON 404 handling and is left as-is: 405 is right for a wrong verb on a
    # real route, and for a path that doesn't exist at all it's arguably wrong
    # (404 would be more defensible) but not something this change touches.
    assert_json_405(client.request(method, path))


def test_matched_api_route_still_works(client):
    response = client.get("/api/get-only")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


@pytest.mark.parametrize(
    "path",
    [
        "/route-that-does-not-exist",
        # Paths that merely start with the letters "api" are web app paths
        "/apiary",
        "/api-keys",
    ],
)
def test_non_api_paths_serve_web_app_404(client, path):
    response = client.get(path)
    assert response.status_code == 404
    assert response.headers.get("content-type", "").startswith("text/html")
    assert WEB_APP_404_BODY in response.text


def test_non_get_method_on_non_api_path_keeps_405(client):
    assert_json_405(client.post("/route-that-does-not-exist"))


def test_api_404s_with_custom_error_handlers(temp_studio):
    # The real server registers the shared error handlers before the web host.
    # This 404 status handler must keep winning over their HTTPException class
    # handler, and neither may reintroduce the HTML 404.
    app = FastAPI()

    @app.get("/api/forced-not-found")
    def forced_not_found():
        raise HTTPException(status_code=404, detail="test missing resource")

    connect_custom_errors(app)
    connect_webhost(app)
    client = TestClient(app)

    assert_json_404(client.get("/api/some-unmatched-path"))
    assert_json_404(client.get("/api/forced-not-found"), "test missing resource")

    web_app_response = client.get("/route-that-does-not-exist")
    assert web_app_response.status_code == 404
    assert WEB_APP_404_BODY in web_app_response.text


def test_non_api_static_file_still_served(temp_studio, client):
    with open(os.path.join(temp_studio, "page.html"), "w", encoding="utf-8") as f:
        f.write("<html><body>real page</body></html>")

    response = client.get("/page")
    assert response.status_code == 200
    assert "real page" in response.text


# The prompt API builds saved prompt IDs as "id::<number>", so every link to a saved
# prompt puts "::" in the URL path. Windows rejects those characters in a filename.
SAVED_PROMPT_ROUTE = "/prompts/project-1/task-1/saved/id::246674517812"


def stat_failing_on(errno_value):
    # Patches os.stat globally (starlette calls the module function directly), narrowed
    # to "::" paths so every other stat still hits the real file system.
    real_stat = os.stat

    def fake_stat(path, *args, **kwargs):
        if "::" in str(path):
            raise OSError(
                errno_value,
                "The filename, directory name, or volume label syntax is incorrect",
            )
        return real_stat(path, *args, **kwargs)

    return patch("starlette.staticfiles.os.stat", fake_stat)


def test_invalid_filename_error_serves_web_app_fallback(client):
    with stat_failing_on(errno.EINVAL):
        response = client.get(SAVED_PROMPT_ROUTE)

    assert response.status_code == 404
    assert WEB_APP_404_BODY in response.text
    # Same response a plain missing route gets: the invalid name is a miss, not a
    # special case the web app has to notice. Indexing raises if a header vanishes.
    plain_miss = client.get("/route-that-does-not-exist")
    assert response.headers["cache-control"] == plain_miss.headers["cache-control"]
    assert response.headers["content-type"] == plain_miss.headers["content-type"]


def test_other_os_errors_still_propagate(client):
    # Only the invalid-filename errno is a miss. Real file system failures must not be
    # hidden behind the web app's fallback page.
    with stat_failing_on(errno.EIO):
        with pytest.raises(OSError) as exc_info:
            client.get(SAVED_PROMPT_ROUTE)

    assert exc_info.value.errno == errno.EIO


def test_invalid_filename_route_served_on_real_filesystem(client):
    # No mocking. On macOS and Linux "::" is an ordinary missing file; on Windows it is
    # an invalid name. Both must reach the same fallback page, which is what the
    # Windows CI job checks against a real Windows file system.
    response = client.get(SAVED_PROMPT_ROUTE)

    assert response.status_code == 404
    assert WEB_APP_404_BODY in response.text
