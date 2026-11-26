from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from kiln_ai.datamodel.model_cache import ModelCache, model_cache_enabled

from kiln_server import server


def test_default_lifespan_enables_model_cache_and_restores_it(monkeypatch):
    monkeypatch.delenv("KILN_DISABLE_MODEL_CACHE", raising=False)
    assert not model_cache_enabled()

    # The module-level app is what the kiln_server script serves.
    with TestClient(server.app):
        assert model_cache_enabled()

    assert not model_cache_enabled()


@pytest.mark.parametrize("env_value, expect_enabled", [("true", False), (None, True)])
def test_default_lifespan_applies_disable_model_cache(
    monkeypatch, env_value, expect_enabled
):
    if env_value is None:
        monkeypatch.delenv("KILN_DISABLE_MODEL_CACHE", raising=False)
    else:
        monkeypatch.setenv("KILN_DISABLE_MODEL_CACHE", env_value)
    # On before startup, so the shutdown restore would turn a cache that was only
    # switched off back on.
    cache = ModelCache(enabled=True)
    monkeypatch.setattr(ModelCache, "_shared_instance", cache)

    with TestClient(server.app):
        assert cache.enabled is expect_enabled

    assert cache.enabled is expect_enabled


def test_caller_lifespan_replaces_default():
    lifespan_ran = False

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        nonlocal lifespan_ran
        lifespan_ran = True
        yield

    with TestClient(server.make_app(lifespan=lifespan)):
        assert lifespan_ran
        assert not model_cache_enabled()
