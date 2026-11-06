from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.testclient import TestClient
from kiln_ai.datamodel.model_cache import model_cache_enabled

from kiln_server import server


def test_default_lifespan_enables_model_cache_and_restores_it():
    assert not model_cache_enabled()

    # The module-level app is what the kiln_server script serves.
    with TestClient(server.app):
        assert model_cache_enabled()

    assert not model_cache_enabled()


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
