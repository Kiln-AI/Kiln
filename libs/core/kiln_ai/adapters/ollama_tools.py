import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, List

import httpx
from pydantic import BaseModel, Field

from kiln_ai.adapters.ml_embedding_model_list import built_in_embedding_models
from kiln_ai.adapters.ml_model_list import ModelProviderName, built_in_models
from kiln_ai.utils.config import Config

logger = logging.getLogger(__name__)

OLLAMA_TIMEOUT_SECONDS = 5
OLLAMA_TAGS_TTL_SECONDS = 60.0


def ollama_base_url() -> str:
    """
    Gets the base URL for Ollama API connections.

    Returns:
        The base URL to use for Ollama API calls: the configured URL if set,
        otherwise the localhost default
    """
    config_base_url = Config.shared().ollama_base_url
    if config_base_url:
        return config_base_url
    return "http://localhost:11434"


def ollama_http_client() -> httpx.AsyncClient:
    """An HTTP client with the timeout and redirect handling Ollama calls need."""
    return httpx.AsyncClient(timeout=OLLAMA_TIMEOUT_SECONDS, follow_redirects=True)


def _installed_model_names(tags: Any) -> frozenset[str] | None:
    if not isinstance(tags, dict) or not isinstance(tags.get("models"), list):
        return None
    return frozenset(
        model["model"]
        for model in tags["models"]
        if isinstance(model, dict) and isinstance(model.get("model"), str)
    )


@dataclass(frozen=True)
class _OllamaTagsSnapshot:
    base_url: str
    installed_models: frozenset[str] | None
    checked_at: float


class OllamaTagCache:
    """
    The model tags installed on the most recently checked Ollama server.

    Holds one server at a time, keyed by its base URL, so a URL change never serves
    another server's tags. A failed check also counts as a check for the TTL (keeping
    the last tags seen for that URL), so an unreachable server costs at most one
    timeout per TTL. Concurrent refreshes on one event loop share a single request.
    """

    def __init__(
        self,
        ttl_seconds: float = OLLAMA_TAGS_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._snapshot: _OllamaTagsSnapshot | None = None
        self._in_flight: tuple[str, asyncio.Task[None]] | None = None

    def installed_models(self, base_url: str) -> frozenset[str] | None:
        """The installed tags last seen at base_url, or None if none are known."""
        snapshot = self._snapshot
        if snapshot is None or snapshot.base_url != base_url:
            return None
        return snapshot.installed_models

    def record(self, base_url: str, tags: Any) -> None:
        """
        Stores an /api/tags response body from base_url. Pass None when the request
        failed; a body that isn't a tag list counts as a failure too.
        """
        installed_models = _installed_model_names(tags)
        if installed_models is None:
            installed_models = self.installed_models(base_url)
        self._snapshot = _OllamaTagsSnapshot(
            base_url=base_url,
            installed_models=installed_models,
            checked_at=self._clock(),
        )

    def is_fresh(self, base_url: str) -> bool:
        snapshot = self._snapshot
        return (
            snapshot is not None
            and snapshot.base_url == base_url
            and self._clock() - snapshot.checked_at < self._ttl_seconds
        )

    async def refresh(self, base_url: str) -> None:
        """Fetches base_url's tags unless they were checked within the TTL."""
        if self.is_fresh(base_url):
            return
        # Shielded so one cancelled caller doesn't cancel the request others await.
        await asyncio.shield(self._shared_fetch(base_url))

    def _shared_fetch(self, base_url: str) -> asyncio.Task[None]:
        # A task belongs to the loop that created it, so callers on another loop
        # (separate asyncio.run calls, test loops) start their own fetch.
        loop = asyncio.get_running_loop()
        if self._in_flight is not None:
            in_flight_url, task = self._in_flight
            if (
                in_flight_url == base_url
                and not task.done()
                and task.get_loop() is loop
            ):
                return task
        task = loop.create_task(self._fetch(base_url))
        self._in_flight = (base_url, task)
        return task

    async def _fetch(self, base_url: str) -> None:
        try:
            async with ollama_http_client() as client:
                response = await client.get(base_url + "/api/tags")
            response.raise_for_status()
            tags = response.json()
        except Exception as e:
            logger.warning(
                "Could not list the models installed in Ollama at %s: %r", base_url, e
            )
            tags = None
        self.record(base_url, tags)


# Process-wide singleton: resolve_ollama_model_variant is sync and called through
# get_litellm_provider_info, so the cache can't be passed in.
_ollama_tag_cache = OllamaTagCache()


def record_ollama_tags(base_url: str, tags: Any) -> None:
    """
    Stores an /api/tags response body from the Ollama server at base_url, for
    resolve_ollama_model_variant. Pass None when the request failed.
    """
    _ollama_tag_cache.record(base_url, tags)


async def ensure_ollama_tags_fresh(provider_name: ModelProviderName) -> None:
    """
    Call before a model-id lookup for provider_name. For Ollama, makes sure the
    installed-tag cache that resolve_ollama_model_variant reads is no older than
    OLLAMA_TAGS_TTL_SECONDS. Does nothing for other providers. Never raises for an
    unreachable server.
    """
    if provider_name != ModelProviderName.ollama:
        return
    await _ollama_tag_cache.refresh(ollama_base_url())


async def ollama_online() -> bool:
    """
    Checks if the Ollama service is available and responding.

    Returns:
        True if Ollama is available and responding, False otherwise
    """
    try:
        async with ollama_http_client() as client:
            await client.get(ollama_base_url() + "/api/tags")
    except httpx.RequestError:
        return False
    return True


class OllamaConnection(BaseModel):
    message: str
    version: str | None = None
    supported_models: List[str]
    untested_models: List[str] = Field(default_factory=list)
    supported_embedding_models: List[str] = Field(default_factory=list)

    def all_models(self) -> List[str]:
        return self.supported_models + self.untested_models

    def all_embedding_models(self) -> List[str]:
        return self.supported_embedding_models


# Parse the Ollama /api/tags response
def parse_ollama_tags(tags: Any) -> OllamaConnection:
    # Build a list of models we support for Ollama from the built-in model list
    supported_ollama_models = set(
        [
            provider.model_id
            for model in built_in_models
            for provider in model.providers
            if provider.name == ModelProviderName.ollama
        ]
    )
    # Append model_aliases to supported_ollama_models
    supported_ollama_models.update(
        [
            alias
            for model in built_in_models
            for provider in model.providers
            for alias in provider.ollama_model_aliases or []
        ]
    )

    supported_ollama_embedding_models = set(
        [
            provider.model_id
            for model in built_in_embedding_models
            for provider in model.providers
            if provider.name == ModelProviderName.ollama
        ]
    )
    supported_ollama_embedding_models.update(
        [
            alias
            for model in built_in_embedding_models
            for provider in model.providers
            for alias in provider.ollama_model_aliases or []
        ]
    )

    if "models" in tags:
        models = tags["models"]
        if isinstance(models, list):
            model_names = [model["model"] for model in models]
            available_supported_models = []
            untested_models = []
            supported_models_latest_aliases = set(
                [f"{m}:latest" for m in supported_ollama_models]
            )
            supported_embedding_models_latest_aliases = set(
                [f"{m}:latest" for m in supported_ollama_embedding_models]
            )

            for model in model_names:
                # Skip embedding models - they should only appear in supported_embedding_models
                if (
                    model in supported_ollama_embedding_models
                    or model in supported_embedding_models_latest_aliases
                ):
                    continue

                if (
                    model in supported_ollama_models
                    or model in supported_models_latest_aliases
                ):
                    available_supported_models.append(model)
                else:
                    untested_models.append(model)

            available_supported_embedding_models = []
            for model in model_names:
                if (
                    model in supported_ollama_embedding_models
                    or model in supported_embedding_models_latest_aliases
                ):
                    available_supported_embedding_models.append(model)

            if (
                available_supported_models
                or untested_models
                or available_supported_embedding_models
            ):
                return OllamaConnection(
                    message="Ollama connected",
                    supported_models=available_supported_models,
                    untested_models=untested_models,
                    supported_embedding_models=available_supported_embedding_models,
                )

    return OllamaConnection(
        message="Ollama is running, but no supported models are installed. Install one or more supported model, like 'ollama pull phi3.5'.",
        supported_models=[],
        untested_models=[],
        supported_embedding_models=[],
    )


async def get_ollama_connection() -> OllamaConnection | None:
    """
    Gets the connection status for Ollama.
    """
    base_url = ollama_base_url()
    try:
        async with ollama_http_client() as client:
            response = await client.get(base_url + "/api/tags")
        tags = response.json()
    except Exception:
        record_ollama_tags(base_url, None)
        return None

    record_ollama_tags(base_url, tags)
    return parse_ollama_tags(tags)


def ollama_model_installed(conn: OllamaConnection, model_name: str) -> bool:
    all_models = conn.all_models()
    return model_name in all_models or f"{model_name}:latest" in all_models


def ollama_embedding_model_installed(conn: OllamaConnection, model_name: str) -> bool:
    all_embedding_models = conn.all_embedding_models()
    return (
        model_name in all_embedding_models
        or f"{model_name}:latest" in all_embedding_models
    )


def resolve_ollama_model_variant(model_id: str, model_aliases: list[str] | None) -> str:
    """
    Determines which variant of an Ollama model is actually installed - different slugs
    may point to the same underlying model via aliases.

    Checks the primary model_id first, then each alias, and returns the first match.
    If none are installed, returns the original model_id (so error messages are clear).

    Reads only the installed-tag cache and does no network IO. Call
    ensure_ollama_tags_fresh first to fill it; with no tags cached for the current
    Ollama URL this returns model_id.

    Returns:
        The model variant that is installed, or the original model_id if none found
    """
    installed_models = _ollama_tag_cache.installed_models(ollama_base_url())
    if installed_models is None:
        return model_id

    for candidate in [model_id, *(model_aliases or [])]:
        if candidate in installed_models or f"{candidate}:latest" in installed_models:
            return candidate

    return model_id
