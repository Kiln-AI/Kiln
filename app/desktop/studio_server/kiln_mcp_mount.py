from fastapi import FastAPI
from kiln_mcp_server import MCP_PATH, build_kiln_mcp_server, default_tmp_root
from starlette.routing import Route

from app.desktop.studio_server._version import __version__


def connect_kiln_mcp_server(app: FastAPI, *, host: str, port: int) -> None:
    """Mount the Kiln MCP server at `MCP_PATH`, for an app bound to `host` and
    `port`. The app's lifespan must run `app.state.kiln_mcp_server.run()`.

    Call it after every API route is added: `call_kiln_api` reaches only the
    routes that exist at this point."""
    server = build_kiln_mcp_server(
        api_app=app,
        app_version=__version__,
        host=host,
        port=port,
        tmp_root=default_tmp_root(),
    )
    app.state.kiln_mcp_server = server
    # What `app.add_route` does; its annotation takes a request handler, not an
    # ASGI app.
    app.router.routes.append(
        Route(MCP_PATH, endpoint=server.asgi_app, include_in_schema=False)
    )
