import json

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient
from kiln_ai.utils import spend_ledger

from app.desktop.studio_server.budget_middleware import BudgetContextMiddleware

CONVERSATION_ID = "1f2e3d4c-5b6a-4789-8abc-def012345678"


def build_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(BudgetContextMiddleware)

    @app.get("/probe")
    def probe():
        return {"conversation_id": spend_ledger.current_conversation_id.get()}

    @app.get("/probe-stream")
    def probe_stream():
        # Mirrors the eval SSE endpoints: the generator body must still see
        # the contextvar even though it is iterated by the response machinery,
        # not the endpoint function.
        async def gen():
            yield json.dumps(
                {"conversation_id": spend_ledger.current_conversation_id.get()}
            )

        return StreamingResponse(gen(), media_type="text/event-stream")

    return app


def test_header_sets_contextvar():
    client = TestClient(build_app())
    r = client.get(
        "/probe", headers={spend_ledger.CONVERSATION_ID_HEADER: CONVERSATION_ID}
    )
    assert r.json() == {"conversation_id": CONVERSATION_ID}


def test_no_header_leaves_contextvar_unset():
    client = TestClient(build_app())
    r = client.get("/probe")
    assert r.json() == {"conversation_id": None}


def test_invalid_header_ignored():
    client = TestClient(build_app())
    r = client.get(
        "/probe", headers={spend_ledger.CONVERSATION_ID_HEADER: "not-a-uuid"}
    )
    assert r.json() == {"conversation_id": None}


def test_contextvar_propagates_into_streaming_response_body():
    client = TestClient(build_app())
    r = client.get(
        "/probe-stream",
        headers={spend_ledger.CONVERSATION_ID_HEADER: CONVERSATION_ID},
    )
    assert json.loads(r.text) == {"conversation_id": CONVERSATION_ID}
