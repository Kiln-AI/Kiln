import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from kiln_server.custom_errors import (
    connect_custom_errors,
    format_error_loc,
)


@pytest.fixture
def app():
    app = FastAPI()
    connect_custom_errors(app)

    class Item(BaseModel):
        name: str = Field(..., min_length=3)
        price: float = Field(..., gt=0)

    @app.post("/items")
    async def create_item(item: Item):
        return item

    @app.get("/timeout")
    async def raise_timeout():
        raise httpx.TimeoutException("Request timed out")

    @app.get("/generic-error")
    async def raise_generic_error():
        raise RuntimeError("Something went wrong")

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
    def test_timeout_exception_returns_408(self, client):
        response = client.get("/timeout")
        assert response.status_code == 408

    def test_timeout_exception_message(self, client):
        response = client.get("/timeout")
        body = response.json()
        assert body["message"] == "Request timed out. Please try again."
        assert "raw_error" in body

    def test_timeout_exception_has_cors_header(self, client):
        response = client.get("/timeout")
        assert response.headers.get("access-control-allow-origin") == "*"

    def test_other_exceptions_still_return_500(self, client_no_raise):
        response = client_no_raise.get("/generic-error")
        assert response.status_code == 500
