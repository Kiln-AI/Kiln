"""Fixtures for the grounding prototype's tests: a saved project and an OpenEnv server record
pointing at the test server in `kiln_ai.openenv.testing`."""

import pytest
from kiln_ai.datamodel.openenv import OpenEnvServer
from kiln_ai.datamodel.project import Project
from kiln_ai.openenv.testing import ENV_NAME, ENV_VERSION, serve_in_thread

RESET_SCHEMA = {
    "type": "object",
    "properties": {
        "seed": {"type": "integer"},
        "fixture_id": {
            "type": "string",
            "description": "The starting data.",
            "enum": ["alpha", "beta"],
        },
    },
}
"""The reset schema the test server publishes at `/schema`."""

README = "The counter keeps notes."


@pytest.fixture
def reset_schema():
    """The reset schema the test server publishes at `/schema`."""
    return RESET_SCHEMA


@pytest.fixture
def server_readme():
    """The readme the test server reports at `/metadata`."""
    return README


@pytest.fixture
def project(tmp_path):
    path = tmp_path / "proj" / "project.kiln"
    path.parent.mkdir(parents=True)
    p = Project(name="proj", path=path)
    p.save_to_file()
    return p


@pytest.fixture
def server_url():
    """Holds one session, so an episode left open blocks the next reset."""
    with serve_in_thread(
        max_sessions=1,
        metadata={
            "name": ENV_NAME,
            "version": ENV_VERSION,
            "description": "test env",
            "readme_content": README,
        },
        extra_routes={"/schema": {"reset": RESET_SCHEMA}},
    ) as base_url:
        yield base_url


@pytest.fixture
def openenv_server(project, server_url):
    server = OpenEnvServer(name="counter", parent=project, url=server_url)
    server.save_to_file()
    return server
