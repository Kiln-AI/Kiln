from unittest.mock import patch

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from kiln_ai.adapters.errors import KilnRunError
from kiln_ai.adapters.provider_tools import ProviderNotConnectedError
from kiln_ai.utils.open_ai_types import ChatCompletionMessageParam
from openai.types.chat import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)
from pydantic import BaseModel, Field, field_validator

from kiln_server.custom_errors import (
    connect_custom_errors,
    dangling_reference_error,
    format_error_loc,
    not_found_error,
    validation_error_message,
)
from kiln_server.error_codes import CHAT_CLIENT_VERSION_TOO_OLD


@pytest.fixture
def app():
    app = FastAPI()
    connect_custom_errors(app)

    class Item(BaseModel):
        name: str = Field(..., min_length=3)
        price: float = Field(..., gt=0)

    class Note(BaseModel):
        text: str

        @field_validator("text")
        @classmethod
        def text_is_not_blank(cls, value: str) -> str:
            if not value.strip():
                raise ValueError("Text must not be blank")
            return value

    @app.post("/items")
    async def create_item(item: Item):
        return item

    @app.post("/item_ids")
    async def delete_items(item_ids: list[str]):
        return item_ids

    @app.post("/notes")
    async def create_note(note: Note):
        return note

    @app.get("/provider-not-connected")
    async def raise_provider_not_connected():
        raise ProviderNotConnectedError(
            "Attempted to use OpenAI without an API key set."
        )

    @app.get("/timeout")
    async def raise_timeout():
        raise httpx.TimeoutException("Request timed out")

    @app.get("/generic-error")
    async def raise_generic_error():
        raise RuntimeError("Something went wrong")

    @app.get("/http-error-string")
    async def raise_http_error_string():
        raise HTTPException(status_code=400, detail="bad request")

    @app.get("/http-error-dict")
    async def raise_http_error_dict():
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Update required",
                "code": CHAT_CLIENT_VERSION_TOO_OLD,
            },
        )

    @app.get("/kiln-run-error-no-trace")
    async def raise_kiln_run_error_no_trace():
        raise KilnRunError(
            message="Rate limit exceeded. Wait a moment and try again.",
            partial_trace=None,
            original=RuntimeError("original failure"),
        )

    @app.get("/kiln-run-error-with-trace")
    async def raise_kiln_run_error_with_trace():
        trace: list[ChatCompletionMessageParam] = [
            ChatCompletionSystemMessageParam(
                role="system", content="You are a helpful assistant."
            ),
            ChatCompletionUserMessageParam(role="user", content="Hi"),
            ChatCompletionAssistantMessageParam(role="assistant", content="Hello!"),
        ]
        raise KilnRunError(
            message="The model's output didn't match the expected format.",
            partial_trace=trace,
            original=ValueError("schema mismatch"),
        )

    return app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def client_no_raise(app):
    return TestClient(app, raise_server_exceptions=False)


def test_validation_error_single_field(client):
    response = client.post("/items", json={"name": "ab", "price": 10})
    assert response.status_code == 422
    res = response.json()
    assert res["message"] == "Name: String should have at least 3 characters"
    assert res["error_messages"] == [
        "Name: String should have at least 3 characters",
    ]
    assert len(res["source_errors"]) == 1


def test_validation_error_multiple_fields(client):
    response = client.post("/items", json={"name": "ab", "price": -5})
    assert response.status_code == 422
    res = response.json()
    assert res["error_messages"] == [
        "Name: String should have at least 3 characters",
        "Price: Input should be greater than 0",
    ]
    assert (
        res["message"]
        == "Name: String should have at least 3 characters.\nPrice: Input should be greater than 0"
    )
    assert len(res["source_errors"]) == 2


def test_invalid_json_body_message(client):
    response = client.post(
        "/items",
        content="not json",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    res = response.json()
    assert res["message"] == (
        "Request body is not valid JSON (Expecting value, at character 0). "
        "Send a JSON value that matches the endpoint's schema."
    )
    assert res["source_errors"][0]["type"] == "json_invalid"


def test_body_level_error_says_request_body(client):
    response = client.post("/item_ids", json={"ids": ["a"]})
    assert response.status_code == 422
    assert response.json()["message"] == "Request body: Input should be a valid list"


def test_value_error_prefix_is_dropped(client):
    response = client.post("/notes", json={"text": " "})
    assert response.status_code == 422
    res = response.json()
    assert res["error_messages"] == ["Text: Text must not be blank"]
    assert res["source_errors"][0]["msg"] == "Value error, Text must not be blank"


@pytest.mark.parametrize(
    "msg, expected",
    [
        ("Value error, Bad value", "Field: Bad value"),
        ("Assertion failed, Must hold", "Field: Must hold"),
        ("Input should be a valid string", "Field: Input should be a valid string"),
        (
            "String should match pattern '^[A-Za-z0-9 _-]+$'",
            "Field: must consist of only letters, numbers, spaces, hyphens, and underscores",
        ),
    ],
)
def test_validation_error_message(msg, expected):
    assert validation_error_message({"msg": msg, "loc": ("body", "field")}) == expected


def test_not_found_error():
    error = not_found_error("Eval config", "123", "eval's configs")
    assert error.status_code == 404
    assert error.detail == (
        "Eval config not found. ID: 123. "
        "Check the ID, or list the eval's configs to find the right one."
    )


def test_provider_not_connected_is_400(client):
    response = client.get("/provider-not-connected")
    assert response.status_code == 400
    assert response.json() == {
        "message": "Attempted to use OpenAI without an API key set.\n"
        "Connect it in the Kiln app under Settings > AI Providers, or choose a "
        "model from a connected provider."
    }
    assert response.headers["Access-Control-Allow-Origin"] == "*"


def test_dangling_reference_error():
    error = dangling_reference_error("RAG config", "extractor config", "123")
    assert error.status_code == 404
    assert error.detail == (
        "The RAG config refers to extractor config 123, which no longer exists."
    )


def test_valid_input(client):
    response = client.post("/items", json={"name": "abc", "price": 10})
    assert response.status_code == 200
    assert response.json() == {"name": "abc", "price": 10}


def test_format_none():
    assert format_error_loc(None) == ""


def test_format_error_loc_empty():
    assert format_error_loc(()) == ""


def test_format_error_loc_single_string():
    assert format_error_loc(("body",)) == ""


def test_format_error_loc_multiple_strings():
    assert format_error_loc(("body", "username")) == "Username"


def test_format_error_loc_with_integer():
    assert format_error_loc(("items", 0, "name")) == "Items[0].Name"


def test_format_error_loc_mixed_types():
    assert format_error_loc(("query", "filter", 2, "value")) == "Query.Filter[2].Value"


def test_format_error_loc_with_none():
    assert format_error_loc(("container", None, "field")) == "Container.Field"


def test_format_error_loc_with_empty_string():
    assert format_error_loc(("container", "", "field")) == "Container.Field"


class TestTimeoutErrorHandler:
    def test_timeout_exception_returns_408(self, client_no_raise):
        response = client_no_raise.get("/timeout")
        assert response.status_code == 408

    def test_timeout_exception_message(self, client_no_raise):
        response = client_no_raise.get("/timeout")
        body = response.json()
        assert body["message"] == "Request timed out. Please try again."
        assert "raw_error" not in body

    def test_timeout_exception_has_cors_header(self, client_no_raise):
        response = client_no_raise.get("/timeout")
        assert response.headers.get("access-control-allow-origin") == "*"

    def test_other_exceptions_still_return_500(self, client_no_raise):
        response = client_no_raise.get("/generic-error")
        assert response.status_code == 500


class TestHTTPExceptionHandler:
    def test_string_detail(self, client_no_raise):
        response = client_no_raise.get("/http-error-string")
        assert response.status_code == 400
        body = response.json()
        assert body == {"message": "bad request"}

    def test_dict_detail_preserves_structure(self, client_no_raise):
        response = client_no_raise.get("/http-error-dict")
        assert response.status_code == 400
        body = response.json()
        assert body == {
            "message": {
                "message": "Update required",
                "code": CHAT_CLIENT_VERSION_TOO_OLD,
            }
        }

    def test_dict_detail_has_cors_header(self, client_no_raise):
        response = client_no_raise.get("/http-error-dict")
        assert response.headers.get("access-control-allow-origin") == "*"


class TestKilnRunErrorHandler:
    def test_kiln_run_error_handler_returns_500(self, client_no_raise):
        response = client_no_raise.get("/kiln-run-error-no-trace")
        assert response.status_code == 500

    def test_kiln_run_error_handler_body_shape(self, client_no_raise):
        response = client_no_raise.get("/kiln-run-error-with-trace")
        body = response.json()
        assert set(body.keys()) == {"message", "error_type", "trace"}
        assert body["message"] == "The model's output didn't match the expected format."
        assert body["error_type"] == "ValueError"
        # No legacy HTTPException keys should leak in.
        assert "detail" not in body
        assert "raw_error" not in body

    def test_kiln_run_error_handler_trace_none(self, client_no_raise):
        response = client_no_raise.get("/kiln-run-error-no-trace")
        body = response.json()
        assert body["trace"] is None
        assert body["error_type"] == "RuntimeError"

    def test_kiln_run_error_handler_trace_populated(self, client_no_raise):
        response = client_no_raise.get("/kiln-run-error-with-trace")
        body = response.json()
        assert isinstance(body["trace"], list)
        assert len(body["trace"]) == 3
        assert body["trace"][0]["role"] == "system"
        assert body["trace"][1]["content"] == "Hi"
        assert body["trace"][2]["role"] == "assistant"

    def test_kiln_run_error_handler_cors_header(self, client_no_raise):
        response = client_no_raise.get("/kiln-run-error-no-trace")
        assert response.headers.get("access-control-allow-origin") == "*"

    def test_kiln_run_error_handler_uses_logger_exception(self, client_no_raise):
        # Guard against future refactors that might switch to logger.error() or
        # drop exc_info. We verify the handler specifically invokes
        # logger.exception with exc_info=exc.original — i.e., the ORIGINAL
        # exception, not the KilnRunError wrapper.
        with patch("kiln_server.custom_errors.logger") as mock_logger:
            response = client_no_raise.get("/kiln-run-error-no-trace")
        assert response.status_code == 500
        mock_logger.exception.assert_called_once()
        _args, kwargs = mock_logger.exception.call_args
        passed_exc = kwargs["exc_info"]
        assert isinstance(passed_exc, RuntimeError)
        assert not isinstance(passed_exc, KilnRunError)
        assert str(passed_exc) == "original failure"
