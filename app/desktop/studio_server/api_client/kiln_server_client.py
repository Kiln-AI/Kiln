import os
from importlib.metadata import version

from app.desktop.studio_server.api_client.kiln_ai_server_client.client import (
    Client as KilnServerClient,
)


def _get_desktop_app_version() -> str:
    """Get the version of the kiln-studio-desktop package."""
    try:
        return version("kiln-studio-desktop")
    except Exception:
        return "unknown"


def get_kiln_server_client() -> KilnServerClient:
    app_version = _get_desktop_app_version()
    base_url = os.getenv("KILN_SERVER_BASE_URL", "https://api.kiln.tech")
    return KilnServerClient(
        base_url=base_url,
        headers={
            "User-Agent": f"KilnDesktopApp/{app_version}",
            "Kiln-Desktop-App-Version": app_version,
        },
    )


server_client = get_kiln_server_client()
"""The default client for the Kiln server for reusability."""
