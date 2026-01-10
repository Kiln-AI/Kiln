import os
from importlib.metadata import version

import httpx
from app.desktop.studio_server.api_client.kiln_ai_server_client.client import (
    AuthenticatedClient,
)
from app.desktop.studio_server.api_client.kiln_ai_server_client.client import (
    Client as KilnServerClient,
)


def _get_desktop_app_version() -> str:
    """Get the version of the kiln-studio-desktop package."""
    try:
        return version("kiln-studio-desktop")
    except Exception:
        return "unknown"


def _get_base_url() -> str:
    """Get the base URL for the Kiln server."""
    return os.getenv("KILN_SERVER_BASE_URL", "https://api.kiln.tech")


def _get_common_headers() -> dict[str, str]:
    """Get common headers for all Kiln server requests."""
    app_version = _get_desktop_app_version()
    return {
        "User-Agent": f"KilnDesktopApp/{app_version}",
        "Kiln-Desktop-App-Version": app_version,
    }


def get_kiln_server_client() -> KilnServerClient:
    """Get a non-authenticated client for the Kiln server."""
    return KilnServerClient(
        base_url=_get_base_url(),
        headers=_get_common_headers(),
    )


def get_authenticated_client(api_key: str) -> AuthenticatedClient:
    """Get an authenticated client for the Kiln server with the provided API key."""
    print(f"Getting authenticated client with API key: {api_key}")
    print(f"Base URL: {_get_base_url()}")
    print(f"Common headers: {_get_common_headers()}")
    return AuthenticatedClient(
        base_url=_get_base_url(),
        token=api_key,
        headers=_get_common_headers(),
        timeout=httpx.Timeout(timeout=300.0, connect=30.0),
    )


server_client = get_kiln_server_client()
"""The default client for the Kiln server for reusability."""
