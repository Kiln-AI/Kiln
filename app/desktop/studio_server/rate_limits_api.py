import os
from typing import Any, Dict

import yaml
from fastapi import FastAPI, HTTPException
from kiln_ai.utils.config import Config


def get_rate_limits_path() -> str:
    settings_dir = Config.settings_dir(create=True)
    return os.path.join(settings_dir, "rate_limits.yaml")


def load_rate_limits() -> Dict[str, Any]:
    rate_limits_path = get_rate_limits_path()
    if not os.path.isfile(rate_limits_path):
        return {}
    with open(rate_limits_path, "r") as f:
        rate_limits = yaml.safe_load(f.read()) or {}
    return rate_limits


def save_rate_limits(rate_limits: Dict[str, Any]) -> None:
    rate_limits_path = get_rate_limits_path()
    with open(rate_limits_path, "w") as f:
        yaml.dump(rate_limits, f)


def connect_rate_limits(app: FastAPI):
    @app.get("/api/rate_limits")
    def read_rate_limits() -> Dict[str, Any]:
        try:
            return load_rate_limits()
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/rate_limits")
    def update_rate_limits(
        rate_limits: Dict[str, Any],
    ) -> Dict[str, Any]:
        try:
            save_rate_limits(rate_limits)
            return load_rate_limits()
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
