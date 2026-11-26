import pytest


@pytest.fixture(autouse=True)
def kiln_mcp_tmp_root(tmp_path, monkeypatch):
    """Point the MCP temp-file folder of every desktop app built in a test at
    `tmp_path`: the app's lifespan empties that folder at start."""
    root = tmp_path / "kiln_mcp"
    monkeypatch.setattr(
        "app.desktop.studio_server.kiln_mcp_mount.default_tmp_root", lambda: root
    )
    return root
