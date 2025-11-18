import asyncio
import os
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict

import yaml

from kiln_ai.utils.config import Config


class ModelRateLimiter:
    """
    Rate limiter for AI model API calls using asyncio.Semaphore.

    Limits concurrent requests per model/provider combination based on
    rate limits defined in ~/.kiln_ai/rate_limits.yaml.

    The rate limits file supports two levels of limits:
    - provider_limits: Max concurrent requests for all models from a provider
    - model_limits: Max concurrent requests for specific models (takes precedence)

    Usage:
        limiter = ModelRateLimiter()
        async with limiter.limit("openai", "gpt_5"):
            # Make API call here
            result = await call_model()
    """

    def __init__(self, rate_limits: Dict[str, Any] | None = None):
        """
        Initialize the rate limiter.

        Args:
            rate_limits: Optional dict of rate limits. If None, loads from file.
                        Format: {
                            "provider_limits": {provider_name: max_concurrent},
                            "model_limits": {provider_name: {model_name: max_concurrent}}
                        }
                        Also supports legacy format: {provider_name: {model_name: max_concurrent}}
        """
        self._semaphores: Dict[str, asyncio.Semaphore] = {}
        loaded_limits = (
            rate_limits if rate_limits is not None else self._load_rate_limits()
        )
        self._rate_limits = self._normalize_rate_limits(loaded_limits)

    def _load_rate_limits(self) -> Dict[str, Any]:
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

    def _normalize_rate_limits(self, rate_limits: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize rate limits to the new format with provider_limits and model_limits.

        Handles backward compatibility with the old flat format.
        """
        if not rate_limits:
            return {"provider_limits": {}, "model_limits": {}}

        if "provider_limits" in rate_limits or "model_limits" in rate_limits:
            return {
                "provider_limits": rate_limits.get("provider_limits", {}),
                "model_limits": rate_limits.get("model_limits", {}),
            }

        return {"provider_limits": {}, "model_limits": rate_limits}

    def _get_semaphore_key(self, provider: str, model: str | None = None) -> str:
        """
        Generate a unique key for the provider/model combination or provider-only.

        Args:
            provider: The provider name
            model: The model name (None for provider-wide semaphores)
        """
        if model is None:
            return f"{provider}::__provider__"
        return f"{provider}::{model}"

    def _get_semaphore(self, provider: str, model: str) -> asyncio.Semaphore | None:
        """
        Get or create a semaphore for the given provider/model.

        Returns None if no rate limit is configured (unlimited concurrency).
        Checks model-specific limit first, then falls back to provider-wide limit.
        If using provider-wide limit, all models from that provider share the same semaphore.
        """
        model_limits = self._rate_limits.get("model_limits", {})
        model_limit = model_limits.get(provider, {}).get(model)

        if model_limit is not None and model_limit > 0:
            key = self._get_semaphore_key(provider, model)
            if key not in self._semaphores:
                self._semaphores[key] = asyncio.Semaphore(model_limit)
            return self._semaphores[key]

        provider_limits = self._rate_limits.get("provider_limits", {})
        provider_limit = provider_limits.get(provider)

        if provider_limit is not None and provider_limit > 0:
            key = self._get_semaphore_key(provider, None)
            if key not in self._semaphores:
                self._semaphores[key] = asyncio.Semaphore(provider_limit)
            return self._semaphores[key]

        return None

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

        Returns the model-specific limit if set, otherwise the provider-wide limit.
        Returns None if no limit is configured (unlimited).
        """
        model_limits = self._rate_limits.get("model_limits", {})
        model_limit = model_limits.get(provider, {}).get(model)

        if model_limit is not None:
            return model_limit

        provider_limits = self._rate_limits.get("provider_limits", {})
        return provider_limits.get(provider)

    def get_provider_limit(self, provider: str) -> int | None:
        """
        Get the configured provider-wide rate limit.

        Returns None if no limit is configured (unlimited).
        """
        provider_limits = self._rate_limits.get("provider_limits", {})
        return provider_limits.get(provider)

    def set_limit(self, provider: str, model: str, limit: int | None) -> None:
        """
        Set or update the rate limit for a provider/model.

        Args:
            provider: The provider name
            model: The model name
            limit: Max concurrent requests (None or 0 for unlimited)
        """
        model_limits = self._rate_limits.setdefault("model_limits", {})

        if provider not in model_limits:
            model_limits[provider] = {}

        if limit is None or limit <= 0:
            model_limits[provider].pop(model, None)
            if not model_limits[provider]:
                model_limits.pop(provider, None)

            key = self._get_semaphore_key(provider, model)
            self._semaphores.pop(key, None)
        else:
            model_limits[provider][model] = limit

            key = self._get_semaphore_key(provider, model)
            self._semaphores[key] = asyncio.Semaphore(limit)

    def set_provider_limit(self, provider: str, limit: int | None) -> None:
        """
        Set or update the provider-wide rate limit.

        Args:
            provider: The provider name
            limit: Max concurrent requests (None or 0 for unlimited)
        """
        provider_limits = self._rate_limits.setdefault("provider_limits", {})

        if limit is None or limit <= 0:
            provider_limits.pop(provider, None)
        else:
            provider_limits[provider] = limit

        self._semaphores.clear()

    def reload(self) -> None:
        """Reload rate limits from the config file and update semaphores."""
        loaded_limits = self._load_rate_limits()
        self._rate_limits = self._normalize_rate_limits(loaded_limits)
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
