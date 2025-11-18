import logging

import yaml
from fastapi import FastAPI, HTTPException
from kiln_ai.utils.model_rate_limiter import (
    RateLimits,
    get_global_rate_limiter,
    get_rate_limits_path,
    load_rate_limits,
)

logger = logging.getLogger(__name__)


def save_rate_limits(rate_limits: RateLimits) -> None:
    """
    Save rate limits to the config file.

    Args:
        rate_limits: Rate limits configuration
    """
    rate_limits_path = get_rate_limits_path()
    with open(rate_limits_path, "w") as f:
        yaml.dump(rate_limits.model_dump(), f)


def connect_rate_limits(app: FastAPI):
    @app.get("/api/rate_limits")
    def read_rate_limits() -> RateLimits:
        """Get the current rate limits configuration."""
        try:
            return load_rate_limits()
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/rate_limits")
    def update_rate_limits(
        rate_limits: RateLimits,
    ) -> RateLimits:
        """
        Update rate limits configuration and reload the global rate limiter.

        Args:
            rate_limits: New rate limits configuration

        Returns:
            The saved rate limits configuration
        """
        try:
            save_rate_limits(rate_limits)
            get_global_rate_limiter().reload()
            return load_rate_limits()
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
