import mimetypes
import os
import sys

from fastapi import FastAPI, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

# Explicitly add MIME types for most common file types. Several users have reported issues on windows 11, where these should be loaded from the registry, but aren't working.
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/html", ".html")
mimetypes.add_type("image/svg+xml", ".svg")
mimetypes.add_type("image/png", ".png")
mimetypes.add_type("image/jpeg", ".jpg")


def studio_path():
    try:
        # pyinstaller path
        base_path = sys._MEIPASS  # type: ignore
        return os.path.join(base_path, "./web_ui/build")
    except Exception:
        base_path = os.path.join(os.path.dirname(__file__), "..")
        return os.path.join(base_path, "../../app/web_ui/build")


API_PATH_PREFIX = "/api"


def is_api_path(url_path: str) -> bool:
    return url_path == API_PATH_PREFIX or url_path.startswith(f"{API_PATH_PREFIX}/")


def add_no_cache_headers(response: Response):
    # This is already local, disable browser caching to prevent issues of old web-app trying to load old APIs and out of date web-ui
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"


# File server that maps /foo/bar to /foo/bar.html (Starlette StaticFiles only does index.html)
class HTMLStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        # API paths must never be served web app content: StaticFiles in html mode
        # answers any miss with the web app's 404.html instead of raising, which
        # would bypass the JSON 404 handler below. Only guard the methods
        # StaticFiles serves, so other methods keep falling through to its 405.
        # Like the 404 handler below, this assumes an empty ASGI root_path (the
        # desktop server sets none); under a prefix it would need get_route_path.
        request_method = scope.get("method")
        request_path = scope.get("path", "")
        if request_method in ("GET", "HEAD") and is_api_path(request_path):
            raise StarletteHTTPException(status_code=404)

        try:
            response = await super().get_response(path, scope)
            if response.status_code != 404:
                add_no_cache_headers(response)
                return response
        except Exception as e:
            # catching HTTPException explicitly not working for some reason
            if getattr(e, "status_code", None) != 404:
                # Don't raise on 404, fall through to return the .html version
                raise e
        #  Try the .html version of the file if the .html version exists, for 404s
        response = await super().get_response(f"{path}.html", scope)
        add_no_cache_headers(response)
        return response


def connect_webhost(app: FastAPI):
    # Ensure studio_path exists (test servers don't necessarily create it)
    os.makedirs(studio_path(), exist_ok=True)
    # Serves the web UI at root
    app.mount("/", HTMLStaticFiles(directory=studio_path(), html=True), name="studio")

    # add pretty 404s
    @app.exception_handler(404)
    def not_found_exception_handler(request, exc):
        # don't handle /api routes, which return JSON errors
        if is_api_path(request.url.path):
            if isinstance(exc, StarletteHTTPException):
                # "message" matches every other Kiln API error (custom_errors.py), and
                # is the key the web UI reads.
                return JSONResponse(
                    status_code=exc.status_code,
                    content={"message": exc.detail},
                )
            raise exc
        return FileResponse(os.path.join(studio_path(), "404.html"), status_code=404)
