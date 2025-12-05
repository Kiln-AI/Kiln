import asyncio
import logging
import os
import threading
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict

import yaml
from pydantic import BaseModel, Field, ValidationError

from kiln_ai.datamodel.datamodel_enums import ModelProviderName
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
        description="Max concurrent requests per provider (applies to all models from that provider unless overridden by a model-specific limit)",
    )
    model_limits: Dict[str, Dict[str, int]] = Field(
        default_factory=dict,
        description="Max concurrent requests per model (takes precedence over provider limits)",
    )


class ModelRateLimiter:
    """
    Rate limiter for AI model API calls using asyncio.Semaphore.

    Limits concurrent requests per model/provider combination based on
    rate limits defined in the rate limits file.

    The rate limits file supports two levels of limits:
    - provider_limits: Max concurrent requests for all models from a provider
    - model_limits: Max concurrent requests for specific models (takes precedence)

    Usage:
        limiter = ModelRateLimiter.shared()
        async with limiter.limit("openai", "gpt_5"):
            # Make API call here
            result = await call_model()
    """

    _shared_instance: "ModelRateLimiter | None" = None

    def __init__(
        self,
        rate_limits: RateLimits | None = None,
        default_provider_limit: int | None = None,
    ):
        """
        Initialize the rate limiter. If no rate limits are provided, loads from file.
        """
        self._lock = threading.Lock()
        self._semaphores: Dict[str, asyncio.Semaphore] = {}
        self._rate_limits = (
            rate_limits if rate_limits is not None else self.load_rate_limits()
        )
        self._default_provider_limits = self._initialize_default_provider_limits(
            default_provider_limit if default_provider_limit is not None else 10
        )

    @classmethod
    def shared(cls) -> "ModelRateLimiter":
        """
        Get the shared singleton instance of the rate limiter.

        This ensures all adapters share the same rate limiter and semaphores,
        properly enforcing global rate limits across the application.

        Returns:
            ModelRateLimiter: The shared rate limiter instance
        """
        if cls._shared_instance is None:
            cls._shared_instance = cls()
        return cls._shared_instance

    def _initialize_default_provider_limits(
        self, default_provider_limit: int
    ) -> Dict[str, int]:
        """
        Set the default concurrent request limits for each provider.
        """
        limits: Dict[str, int] = defaultdict(lambda: default_provider_limit)
        limits[ModelProviderName.ollama] = 1
        return limits

    @classmethod
    def rate_limits_path(cls) -> str:
        """
        Get the path to the rate limits configuration file.
        """
        settings_dir = Config.settings_dir(create=True)
        return os.path.join(settings_dir, "rate_limits.yaml")

    @classmethod
    def load_rate_limits(cls) -> RateLimits:
        """
        Load rate limits from the config file.

        Returns empty RateLimits if file doesn't exist or is invalid.
        """
        rate_limits_path = cls.rate_limits_path()
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

    def update_rate_limits(self, rate_limits: RateLimits) -> None:
        """
        Update rate limits and save to file. Thread-safe operation.
        """
        with self._lock:
            self._rate_limits = rate_limits
            rate_limits_path = self.rate_limits_path()
            with open(rate_limits_path, "w") as f:
                yaml.dump(self._rate_limits.model_dump(), f)
            self._semaphores.clear()

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

    def _get_semaphore(self, provider: str, model: str) -> asyncio.Semaphore:
        """
        Get or create a semaphore for the given provider/model.

        Checks model-specific limit first, then falls back to provider-wide limit.
        If using provider-wide limit, all models from that provider share the same semaphore.
        If no limit is configured, uses a default value or the model's max_parallel_requests
        defined in the model list.
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

        # if no limit is configured, set a default of 10
        key = self._get_semaphore_key(provider, model)
        if key not in self._semaphores:
            self._semaphores[key] = asyncio.Semaphore(
                self._get_model_default_max_concurrent_requests(provider, model)
            )
        return self._semaphores[key]

    @asynccontextmanager
    async def limit(self, provider: str, model: str) -> AsyncIterator[None]:
        """
        Context manager to limit concurrent requests to a model.

        Usage:
            async with limiter.limit("openai", "gpt_5"):
                result = await make_api_call()
        """
        async with self._get_semaphore(provider, model):
            yield

    def _get_model_limit(self, provider: str, model: str) -> int | None:
        """
        Get the configured rate limit for a provider/model.

        Returns the model-specific limit if set, otherwise the provider-wide limit.
        Returns None if no limit is configured (unlimited).
        """
        model_limit = self._rate_limits.model_limits.get(provider, {}).get(model)
        if model_limit is not None:
            return model_limit
        return self._rate_limits.provider_limits.get(provider)

    def _get_provider_limit(self, provider: str) -> int | None:
        """
        Get the configured provider-wide rate limit.

        Returns None if no limit is configured (unlimited).
        """
        return self._rate_limits.provider_limits.get(provider)

    def _set_model_limit(self, provider: str, model: str, limit: int | None) -> None:
        """
        Set or update the rate limit for a provider/model.
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

    def reload(self) -> None:
        """
        Reload rate limits from the config file and update semaphores.

        Thread-safe operation that ensures consistency during reload.
        """
        with self._lock:
            self._rate_limits = self.load_rate_limits()
            self._semaphores.clear()

    def _get_model_default_max_concurrent_requests(
        self, provider: str, model: str
    ) -> int:
        """
        Get the model-specified max concurrent requests for a provider/model.

        Returns the default max concurrent requests if no limit is configured
        or the provider-wide limit. Whichever is lower.
        """
        # necessary to avoid circular import with ml_model_list
        from kiln_ai.adapters.ml_model_list import built_in_models_from_provider

        model_provider = built_in_models_from_provider(
            ModelProviderName(provider), model
        )
        if (
            model_provider is not None
            and model_provider.max_parallel_requests is not None
        ):
            # use the lower of the model-specific limit or the provider-wide limit
            return min(
                model_provider.max_parallel_requests,
                self._default_provider_limits[provider],
            )

        return self._default_provider_limits[provider]
