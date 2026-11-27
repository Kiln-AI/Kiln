from typing import Callable
from unittest.mock import patch

import httpx
import pytest
import respx

OLLAMA_TEST_URL = "http://ollama.test:11434"


@pytest.fixture
def ollama_api():
    """A fake Ollama server at OLLAMA_TEST_URL, set as the configured Ollama URL."""
    with (
        patch(
            "kiln_ai.adapters.ollama_tools.ollama_base_url",
            return_value=OLLAMA_TEST_URL,
        ),
        respx.mock(base_url=OLLAMA_TEST_URL, assert_all_called=False) as router,
    ):
        yield router


@pytest.fixture
def ollama_installed(ollama_api) -> Callable[..., respx.Route]:
    """Makes the fake Ollama server's /api/tags list the given model tags."""

    def install(*model_names: str) -> respx.Route:
        return ollama_api.get("/api/tags").mock(
            return_value=httpx.Response(
                200, json={"models": [{"model": name} for name in model_names]}
            )
        )

    return install
