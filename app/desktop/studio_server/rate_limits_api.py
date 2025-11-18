import os
from typing import Any, Dict

import yaml
from fastapi import FastAPI, HTTPException
from kiln_ai.adapters.ml_embedding_model_list import built_in_embedding_models
from kiln_ai.adapters.ml_model_list import built_in_models
from kiln_ai.adapters.reranker_list import built_in_rerankers
from kiln_ai.utils.config import Config
from pydantic import BaseModel


class ModelInfo(BaseModel):
    model_name: str
    friendly_name: str
    provider_name: str
    model_id: str | None


class AllModelsResponse(BaseModel):
    normal_models: list[ModelInfo]
    embedding_models: list[ModelInfo]
    reranker_models: list[ModelInfo]


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

    @app.get("/api/models/all")
    def get_all_models() -> AllModelsResponse:
        try:
            normal_models: list[ModelInfo] = []
            for model in built_in_models:
                for provider in model.providers:
                    normal_models.append(
                        ModelInfo(
                            model_name=model.name,
                            friendly_name=model.friendly_name,
                            provider_name=provider.name.value,
                            model_id=provider.model_id,
                        )
                    )

            embedding_models: list[ModelInfo] = []
            for model in built_in_embedding_models:
                for provider in model.providers:
                    embedding_models.append(
                        ModelInfo(
                            model_name=model.name,
                            friendly_name=model.friendly_name,
                            provider_name=provider.name.value,
                            model_id=provider.model_id,
                        )
                    )

            reranker_models: list[ModelInfo] = []
            for model in built_in_rerankers:
                for provider in model.providers:
                    reranker_models.append(
                        ModelInfo(
                            model_name=model.name,
                            friendly_name=model.friendly_name,
                            provider_name=provider.name.value,
                            model_id=provider.model_id,
                        )
                    )

            return AllModelsResponse(
                normal_models=normal_models,
                embedding_models=embedding_models,
                reranker_models=reranker_models,
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
