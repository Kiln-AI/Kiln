from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from kiln_server.custom_errors import connect_custom_errors
from kiln_server.utils.agent_checks import MCP_POLICY_KEY
from kiln_server.utils.agent_checks.policy import ALLOW_AGENT
from pydantic import BaseModel

from app.desktop.studio_server.model_info_api import connect_model_info_api
from app.desktop.studio_server.services.model_info.models_dev import (
    ModelsDevSnapshot,
)

ROUTES = (
    "/api/model_info/models",
    "/api/model_info/model_details",
    "/api/model_info/providers",
)
LOADED_AT = datetime(2026, 11, 22, 6, 0, tzinfo=timezone.utc)


class Offered(BaseModel):
    provider_id: str
    provider_name: str
    models: list[dict]


async def offered_models() -> list[BaseModel]:
    return [
        Offered(
            provider_id="openai",
            provider_name="OpenAI",
            models=[
                {"id": "gpt_4o_mini", "name": "GPT 4o Mini"},
                {"id": "gpt_4o", "name": "GPT 4o"},
            ],
        )
    ]


class FakeSource:
    async def current(self) -> ModelsDevSnapshot:
        return ModelsDevSnapshot(
            data=None, state="stale", loaded_at=LOADED_AT, detail="HTTP 503"
        )


@pytest.fixture
def app() -> FastAPI:
    app = FastAPI()
    connect_custom_errors(app)
    connect_model_info_api(
        app, available_models=offered_models, models_dev=FakeSource()
    )
    return app


@pytest.fixture
def client(app) -> TestClient:
    return TestClient(app)


@pytest.mark.parametrize("path", ROUTES)
def test_every_answer_has_sources(client, path):
    params = {"model_id": "gpt_4o"} if path.endswith("model_details") else {}
    response = client.get(path, params=params)
    assert response.status_code == 200
    sources = response.json()["sources"]
    assert sources["kiln_model_list"]["origin"] in ("built_in", "remote_config")
    assert sources["models_dev"]["state"] == "stale"
    assert sources["models_dev"]["detail"] == "HTTP 503"
    assert sources["models_dev"]["loaded_at"] == "2026-11-22T06:00:00Z"


def test_the_list_parses_repeated_tags_and_booleans(client):
    params = {"provider": "openai", "include_notes": "true", "sort": "price"}
    response = client.get("/api/model_info/models", params={**params, "limit": 1})
    assert response.status_code == 200
    answer = response.json()
    assert answer["total"] == 2 and len(answer["models"]) == 1
    assert answer["models"][0]["providers"] == [
        {
            "provider": "openai",
            "status": "ready",
            "input_price": None,
            "output_price": None,
            "tags": [],
            "deprecated": False,
        }
    ]
    tagged = client.get(
        "/api/model_info/models",
        params={**params, "tags": [f"no_such_tag_{i}" for i in range(12)]},
    )
    assert tagged.status_code == 200 and tagged.json()["total"] == 0


def test_the_list_search_and_paging(client):
    answer = client.get(
        "/api/model_info/models", params={"search": "4o mini", "offset": 0}
    ).json()
    assert answer["models"][0]["model"] == "gpt_4o_mini"
    assert answer["fuzzy_match"] is False
    empty = client.get("/api/model_info/models", params={"offset": 100}).json()
    assert empty["models"] == [] and empty["total"] == 2


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": 201},
        {"offset": -1},
        {"tags": [f"t{i}" for i in range(13)]},
        {"tags": ["x" * 41]},
        {"search": ""},
        {"search": "x" * 101},
        {"sort": "cheapest"},
        {"featured": "maybe"},
    ],
)
def test_bad_list_parameters_are_422(client, params):
    assert client.get("/api/model_info/models", params=params).status_code == 422


def test_an_unknown_provider_is_422(client):
    response = client.get("/api/model_info/models", params={"provider": "google"})
    assert response.status_code == 422
    message = response.json()["message"]
    assert message.startswith("Unknown provider: google. Provider ids: ")
    assert "gemini_api" in message


def test_a_search_without_letters_is_422(client):
    response = client.get("/api/model_info/models", params={"search": "::"})
    assert response.status_code == 422
    assert response.json()["message"] == "search needs at least one letter or digit."


def test_details_of_a_model(client):
    response = client.get(
        "/api/model_info/model_details",
        params={"model_id": "GPT_4O", "provider": "openai"},
    )
    assert response.status_code == 200
    details = response.json()
    assert details["model"] == "gpt_4o"
    assert [(p["provider"], p["status"]) for p in details["providers"]] == [
        ("openai", "ready")
    ]


def test_details_need_a_model_id(client):
    assert client.get("/api/model_info/model_details").status_code == 422


def test_an_unknown_model_is_404(client):
    response = client.get(
        "/api/model_info/model_details", params={"model_id": "gpt_4o_mni"}
    )
    assert response.status_code == 404
    message = response.json()["message"]
    assert message.startswith("Model not found: gpt_4o_mni. Closest ids: gpt_4o_mini")
    assert message.endswith(
        "To find a model id, call GET /api/model_info/models with search=<name>"
        " and include_not_available=true."
    )


def test_a_model_without_the_provider_entry_is_404(client):
    response = client.get(
        "/api/model_info/model_details",
        params={"model_id": "gpt_4o", "provider": "typesafe"},
    )
    assert response.status_code == 404
    assert response.json()["message"].startswith(
        "Model gpt_4o has no entry for provider typesafe. Its providers: "
    )


def test_the_providers_list_marks_connected_ones(client):
    providers = client.get("/api/model_info/providers").json()["providers"]
    assert (providers[0]["provider"], providers[0]["status"]) == ("openai", "connected")
    assert providers[0]["ready_model_count"] == 2
    assert {p["status"] for p in providers[1:]} == {"not_connected"}


@pytest.mark.parametrize("path", ROUTES)
def test_each_route_is_open_to_agents_and_not_mcp_blocked(app, path):
    operation = app.openapi()["paths"][path]["get"]
    assert operation["x-agent-policy"] == ALLOW_AGENT["x-agent-policy"]
    assert MCP_POLICY_KEY not in operation
    assert operation["tags"] == ["Providers & Models"]
    assert operation["summary"] and operation["description"]
