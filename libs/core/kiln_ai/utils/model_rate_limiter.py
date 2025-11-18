import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict

import yaml
from pydantic import BaseModel, Field, ValidationError

from kiln_ai.utils.config import Config

logger = logging.getLogger(__name__)


class RateLimits(BaseModel):
    """
    Rate limits configuration with provider-wide and model-specific limits.

    provider_limits: Max concurrent requests per provider (applies to all models)
    model_limits: Max concurrent requests per model (takes precedence over provider limits)
    """

    provider_limits: Dict[str, int] = Field(
        default_factory=dict,
        description="Max concurrent requests per provider (applies to all models from that provider)",
    )
    model_limits: Dict[str, Dict[str, int]] = Field(
        default_factory=dict,
        description="Max concurrent requests per model (takes precedence over provider limits)",
    )


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

    def __init__(self, rate_limits: RateLimits | None = None):
        """
        Initialize the rate limiter.

        Args:
            rate_limits: Optional RateLimits model. If None, loads from file.
        """
        self._semaphores: Dict[str, asyncio.Semaphore] = {}
        self._rate_limits = (
            rate_limits if rate_limits is not None else load_rate_limits()
        )

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
        model_limit = self._rate_limits.model_limits.get(provider, {}).get(model)

        if model_limit is not None and model_limit > 0:
            key = self._get_semaphore_key(provider, model)
            if key not in self._semaphores:
                self._semaphores[key] = asyncio.Semaphore(model_limit)
            return self._semaphores[key]

        provider_limit = self._rate_limits.provider_limits.get(provider)

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
        model_limit = self._rate_limits.model_limits.get(provider, {}).get(model)
        if model_limit is not None:
            return model_limit
        return self._rate_limits.provider_limits.get(provider)

    def get_provider_limit(self, provider: str) -> int | None:
        """
        Get the configured provider-wide rate limit.

        Returns None if no limit is configured (unlimited).
        """
        return self._rate_limits.provider_limits.get(provider)

    def set_limit(self, provider: str, model: str, limit: int | None) -> None:
        """
        Set or update the rate limit for a provider/model.

        Args:
            provider: The provider name
            model: The model name
            limit: Max concurrent requests (None or 0 for unlimited)
        """
        if provider not in self._rate_limits.model_limits:
            self._rate_limits.model_limits[provider] = {}

        if limit is None or limit <= 0:
            if model in self._rate_limits.model_limits.get(provider, {}):
                del self._rate_limits.model_limits[provider][model]
            if (
                provider in self._rate_limits.model_limits
                and not self._rate_limits.model_limits[provider]
            ):
                del self._rate_limits.model_limits[provider]

            key = self._get_semaphore_key(provider, model)
            self._semaphores.pop(key, None)
        else:
            self._rate_limits.model_limits[provider][model] = limit

            key = self._get_semaphore_key(provider, model)
            self._semaphores[key] = asyncio.Semaphore(limit)

    def set_provider_limit(self, provider: str, limit: int | None) -> None:
        """
        Set or update the provider-wide rate limit.

        Args:
            provider: The provider name
            limit: Max concurrent requests (None or 0 for unlimited)
        """
        if limit is None or limit <= 0:
            if provider in self._rate_limits.provider_limits:
                del self._rate_limits.provider_limits[provider]
        else:
            self._rate_limits.provider_limits[provider] = limit

        self._semaphores.clear()

    def reload(self) -> None:
        """Reload rate limits from the config file and update semaphores."""
        self._rate_limits = load_rate_limits()
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


def get_rate_limits_path() -> str:
    settings_dir = Config.settings_dir(create=True)
    return os.path.join(settings_dir, "rate_limits.yaml")


def load_rate_limits() -> RateLimits:
    """
    Load rate limits from the config file.

    Returns empty RateLimits if file doesn't exist or is invalid.
    """
    rate_limits_path = get_rate_limits_path()
    if not os.path.isfile(rate_limits_path):
        return RateLimits()

    try:
        with open(rate_limits_path, "r") as f:
            data = yaml.safe_load(f.read()) or {}
        return RateLimits(**data)
    except ValidationError as e:
        logger.warning(
            f"Invalid rate limits configuration in {rate_limits_path}: {e}. Using empty rate limits."
        )
        return RateLimits()
    except Exception as e:
        logger.warning(
            f"Failed to load rate limits from {rate_limits_path}: {e}. Using empty rate limits."
        )
        return RateLimits()
