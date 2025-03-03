import mimetypes
import os
import sys

from fastapi import FastAPI, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

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


def add_no_cache_headers(response: Response):
    # This is already local, disable browser caching to prevent issues of old web-app trying to load old APIs and out of date web-ui
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"


# File server that maps /foo/bar to /foo/bar.html (Starlette StaticFiles only does index.html)
class HTMLStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
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
        if request.url.path.startswith("/api"):
            raise exc
        return FileResponse(os.path.join(studio_path(), "404.html"), status_code=404)
