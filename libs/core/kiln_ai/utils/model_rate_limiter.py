import asyncio
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict

import yaml

from kiln_ai.utils.config import Config


class ModelRateLimiter:
    """
    Rate limiter for AI model API calls using asyncio.Semaphore.

    Limits concurrent requests per model/provider combination based on
    rate limits defined in ~/.kiln_ai/rate_limits.yaml.

    Usage:
        limiter = ModelRateLimiter()
        async with limiter.limit("openai", "gpt_5"):
            # Make API call here
            result = await call_model()
    """

    def __init__(self, rate_limits: Dict[str, Dict[str, int]] | None = None):
        """
        Initialize the rate limiter.

        Args:
            rate_limits: Optional dict of rate limits. If None, loads from file.
                        Format: {provider_name: {model_name: max_concurrent}}
        """
        self._semaphores: Dict[str, asyncio.Semaphore] = {}
        self._rate_limits = (
            rate_limits if rate_limits is not None else self._load_rate_limits()
        )

    def _load_rate_limits(self) -> Dict[str, Dict[str, int]]:
        """Load rate limits from the config file."""
        rate_limits_path = os.path.join(
            Config.settings_dir(create=False), "rate_limits.yaml"
        )
        if not os.path.isfile(rate_limits_path):
            return {}
        try:
            with open(rate_limits_path, "r") as f:
                return yaml.safe_load(f.read()) or {}
        except Exception:
            return {}

    def _get_semaphore_key(self, provider: str, model: str) -> str:
        """Generate a unique key for the provider/model combination."""
        return f"{provider}::{model}"

    def _get_semaphore(self, provider: str, model: str) -> asyncio.Semaphore | None:
        """
        Get or create a semaphore for the given provider/model.

        Returns None if no rate limit is configured (unlimited concurrency).
        """
        key = self._get_semaphore_key(provider, model)

        if key in self._semaphores:
            return self._semaphores[key]

        limit = self._rate_limits.get(provider, {}).get(model)

        if limit is None or limit <= 0:
            return None

        semaphore = asyncio.Semaphore(limit)
        self._semaphores[key] = semaphore
        return semaphore

    @asynccontextmanager
    async def limit(self, provider: str, model: str) -> AsyncIterator[None]:
        """
        Context manager to limit concurrent requests to a model.

        Args:
            provider: The provider name (e.g., "openai", "anthropic")
            model: The model name (e.g., "gpt_5", "claude_opus_4_1")

        Usage:
            async with limiter.limit("openai", "gpt_5"):
                result = await make_api_call()
        """
        semaphore = self._get_semaphore(provider, model)

        if semaphore is None:
            yield
        else:
            async with semaphore:
                yield

    def get_limit(self, provider: str, model: str) -> int | None:
        """
        Get the configured rate limit for a provider/model.

        Returns None if no limit is configured (unlimited).
        """
        return self._rate_limits.get(provider, {}).get(model)

    def set_limit(self, provider: str, model: str, limit: int | None) -> None:
        """
        Set or update the rate limit for a provider/model.

        Args:
            provider: The provider name
            model: The model name
            limit: Max concurrent requests (None or 0 for unlimited)
        """
        if provider not in self._rate_limits:
            self._rate_limits[provider] = {}

        if limit is None or limit <= 0:
            self._rate_limits[provider].pop(model, None)
            if not self._rate_limits[provider]:
                self._rate_limits.pop(provider, None)

            key = self._get_semaphore_key(provider, model)
            self._semaphores.pop(key, None)
        else:
            self._rate_limits[provider][model] = limit

            key = self._get_semaphore_key(provider, model)
            self._semaphores[key] = asyncio.Semaphore(limit)

    def reload(self) -> None:
        """Reload rate limits from the config file and update semaphores."""
        self._rate_limits = self._load_rate_limits()
        self._semaphores.clear()


# Global singleton instance
_global_rate_limiter: ModelRateLimiter | None = None


def get_global_rate_limiter() -> ModelRateLimiter:
    """
    Get the global rate limiter instance (singleton).

    This ensures all adapters share the same rate limiter and semaphores,
    properly enforcing global rate limits across the application.

    Returns:
        ModelRateLimiter: The global rate limiter instance
    """
    global _global_rate_limiter
    if _global_rate_limiter is None:
        _global_rate_limiter = ModelRateLimiter()
    return _global_rate_limiter


def reset_global_rate_limiter() -> None:
    """
    Reset the global rate limiter instance.

    This is primarily used for testing to ensure a clean state between tests.
    """
    global _global_rate_limiter
    _global_rate_limiter = None
