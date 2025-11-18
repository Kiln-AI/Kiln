import logging

from fastapi import FastAPI, HTTPException
from kiln_ai.utils.model_rate_limiter import ModelRateLimiter, RateLimits

logger = logging.getLogger(__name__)


def connect_rate_limits(app: FastAPI):
    @app.get("/api/rate_limits")
    def read_rate_limits() -> RateLimits:
        """Get the current rate limits configuration."""
        try:
            return ModelRateLimiter.load_rate_limits()
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/rate_limits")
    def update_rate_limits(
        rate_limits: RateLimits,
    ) -> RateLimits:
        """
        Update rate limits configuration on the shared rate limiter.

        Args:
            rate_limits: New rate limits configuration

        Returns:
            The saved rate limits configuration
        """
        try:
            # Update the shared singleton (thread-safe, saves to file, clears semaphores)
            ModelRateLimiter.shared().update_rate_limits(rate_limits)
            return ModelRateLimiter.load_rate_limits()
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
