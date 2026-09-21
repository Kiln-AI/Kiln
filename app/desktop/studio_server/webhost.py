import errno
import mimetypes
import os
import sys

from fastapi import FastAPI, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
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

# Served in place of the web app when app/web_ui/build has no compiled UI in it.
# That directory is a build artifact, and nothing in the dev server builds it, so a
# fresh clone reaches this instead of the studio. Without it the 404 handler below
# tries to serve a 404.html that isn't there and the request dies as a 500.
WEB_UI_MISSING_HTML = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Kiln &mdash; web UI not built</title>
    <style>
      :root { color-scheme: light dark; }
      body {
        margin: 0;
        min-height: 100vh;
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 24px;
        box-sizing: border-box;
        background: #f2f2f7;
        color: #1c1c1e;
        font: 16px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
          Helvetica, Arial, sans-serif;
      }
      main { max-width: 34rem; width: 100%; }
      h1 { font-size: 1.5rem; line-height: 1.3; margin: 0 0 0.75rem; }
      h2 { font-size: 0.8125rem; letter-spacing: 0.04em; text-transform: uppercase;
           opacity: 0.55; margin: 2rem 0 0.5rem; }
      p { margin: 0 0 0.5rem; }
      code, pre {
        font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
        font-size: 0.875rem;
      }
      code { background: rgba(120, 120, 128, 0.16); padding: 0.1em 0.35em;
             border-radius: 5px; }
      pre { background: rgba(120, 120, 128, 0.16); padding: 0.75rem 1rem;
            border-radius: 10px; overflow-x: auto; margin: 0; }
      a { color: #0071e3; }
      @media (prefers-color-scheme: dark) {
        body { background: #1c1c1e; color: #f2f2f7; }
        a { color: #4da3ff; }
      }
    </style>
  </head>
  <body>
    <main>
      <h1>The Kiln web UI isn&rsquo;t built yet</h1>
      <p>
        This server serves the compiled web UI from <code>app/web_ui/build</code>,
        and nothing is there.
      </p>

      <h2>Working on the web UI?</h2>
      <p>
        Run <code>make ui</code> in a second terminal and open
        <a href="http://localhost:5173/run">localhost:5173/run</a>. That server
        hot-reloads your changes; this one serves a fixed build.
      </p>

      <h2>Just want the app on this port?</h2>
      <p>Build it once, then reload this page:</p>
      <pre>cd app/web_ui &amp;&amp; npm run build</pre>
    </main>
  </body>
</html>
"""


def is_api_path(url_path: str) -> bool:
    return url_path == API_PATH_PREFIX or url_path.startswith(f"{API_PATH_PREFIX}/")


def add_no_cache_headers(response: Response):
    # This is already local, disable browser caching to prevent issues of old web-app trying to load old APIs and out of date web-ui
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"


# File server that maps /foo/bar to /foo/bar.html (Starlette StaticFiles only does index.html)
class HTMLStaticFiles(StaticFiles):
    def lookup_path(self, path: str) -> tuple[str, os.stat_result | None]:
        try:
            return super().lookup_path(path)
        except OSError as e:
            # Windows raises EINVAL for names with "::" (our saved-prompt routes: "id::123").
            # No file can exist there, so return StaticFiles' own miss sentinel and let the
            # html fallback serve the route, exactly as a miss does on macOS and Linux.
            if e.errno != errno.EINVAL:
                raise
            return "", None

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

        not_found_page = os.path.join(studio_path(), "404.html")
        if not os.path.isfile(not_found_page):
            # 503 rather than 404: the route may well be fine, there is just no web
            # UI to serve it with.
            response = HTMLResponse(content=WEB_UI_MISSING_HTML, status_code=503)
            # So the page a developer left open picks the app up once they build it.
            add_no_cache_headers(response)
            return response

        return FileResponse(not_found_page, status_code=404)
