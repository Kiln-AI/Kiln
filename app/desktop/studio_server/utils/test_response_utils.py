import json
from http import HTTPStatus
from unittest.mock import MagicMock

import pytest
from app.desktop.studio_server.utils.response_utils import check_response_error
from fastapi import HTTPException


def _make_response(status_code: HTTPStatus, content: bytes) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.content = content
    return resp


@pytest.mark.parametrize(
    "status_code",
    [HTTPStatus.OK, HTTPStatus.CREATED, HTTPStatus.ACCEPTED, HTTPStatus.NO_CONTENT],
)
def test_2xx_does_not_raise(status_code: HTTPStatus):
    resp = _make_response(status_code, b"")
    check_response_error(resp)


@pytest.mark.parametrize(
    "status_code",
    [HTTPStatus.BAD_REQUEST, HTTPStatus.INTERNAL_SERVER_ERROR, HTTPStatus.FORBIDDEN],
)
def test_non_200_with_json_message(status_code: HTTPStatus):
    body = json.dumps({"message": "Something went wrong"}).encode()
    resp = _make_response(status_code, body)

    with pytest.raises(HTTPException) as exc_info:
        check_response_error(resp)

    assert exc_info.value.status_code == status_code
    assert exc_info.value.detail == "Something went wrong"


def test_non_200_with_json_missing_message_uses_default():
    body = json.dumps({"error": "no message key here"}).encode()
    resp = _make_response(HTTPStatus.BAD_REQUEST, body)

    with pytest.raises(HTTPException) as exc_info:
        check_response_error(resp)

    assert exc_info.value.detail == "Unknown error."


def test_non_200_with_custom_default_detail():
    resp = _make_response(HTTPStatus.BAD_REQUEST, b"not json")

    with pytest.raises(HTTPException) as exc_info:
        check_response_error(resp, default_detail="Custom default")

    assert exc_info.value.detail == "Custom default"


def test_non_200_with_invalid_json_uses_default():
    resp = _make_response(HTTPStatus.BAD_REQUEST, b"{invalid json")

    with pytest.raises(HTTPException) as exc_info:
        check_response_error(resp)

    assert exc_info.value.detail == "Unknown error."


def test_non_200_with_non_json_content_uses_default():
    resp = _make_response(HTTPStatus.INTERNAL_SERVER_ERROR, b"plain text error")

    with pytest.raises(HTTPException) as exc_info:
        check_response_error(resp)

    assert exc_info.value.detail == "Unknown error."
