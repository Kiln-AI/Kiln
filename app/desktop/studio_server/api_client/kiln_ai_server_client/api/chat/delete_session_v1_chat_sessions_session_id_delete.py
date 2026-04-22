from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.delete_session_v1_chat_sessions_session_id_delete_response_400 import (
    DeleteSessionV1ChatSessionsSessionIdDeleteResponse400,
)
from ...models.delete_session_v1_chat_sessions_session_id_delete_response_404 import (
    DeleteSessionV1ChatSessionsSessionIdDeleteResponse404,
)
from ...models.delete_session_v1_chat_sessions_session_id_delete_response_426 import (
    DeleteSessionV1ChatSessionsSessionIdDeleteResponse426,
)
from ...models.delete_session_v1_chat_sessions_session_id_delete_response_500 import (
    DeleteSessionV1ChatSessionsSessionIdDeleteResponse500,
)
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    session_id: str,
) -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "delete",
        "url": "/v1/chat/sessions/{session_id}".format(
            session_id=quote(str(session_id), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> (
    Any
    | DeleteSessionV1ChatSessionsSessionIdDeleteResponse400
    | DeleteSessionV1ChatSessionsSessionIdDeleteResponse404
    | DeleteSessionV1ChatSessionsSessionIdDeleteResponse426
    | DeleteSessionV1ChatSessionsSessionIdDeleteResponse500
    | HTTPValidationError
    | None
):
    if response.status_code == 204:
        response_204 = cast(Any, None)
        return response_204

    if response.status_code == 400:
        response_400 = DeleteSessionV1ChatSessionsSessionIdDeleteResponse400.from_dict(response.json())

        return response_400

    if response.status_code == 404:
        response_404 = DeleteSessionV1ChatSessionsSessionIdDeleteResponse404.from_dict(response.json())

        return response_404

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())

        return response_422

    if response.status_code == 426:
        response_426 = DeleteSessionV1ChatSessionsSessionIdDeleteResponse426.from_dict(response.json())

        return response_426

    if response.status_code == 500:
        response_500 = DeleteSessionV1ChatSessionsSessionIdDeleteResponse500.from_dict(response.json())

        return response_500

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[
    Any
    | DeleteSessionV1ChatSessionsSessionIdDeleteResponse400
    | DeleteSessionV1ChatSessionsSessionIdDeleteResponse404
    | DeleteSessionV1ChatSessionsSessionIdDeleteResponse426
    | DeleteSessionV1ChatSessionsSessionIdDeleteResponse500
    | HTTPValidationError
]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    session_id: str,
    *,
    client: AuthenticatedClient,
) -> Response[
    Any
    | DeleteSessionV1ChatSessionsSessionIdDeleteResponse400
    | DeleteSessionV1ChatSessionsSessionIdDeleteResponse404
    | DeleteSessionV1ChatSessionsSessionIdDeleteResponse426
    | DeleteSessionV1ChatSessionsSessionIdDeleteResponse500
    | HTTPValidationError
]:
    """Delete Session

    Args:
        session_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | DeleteSessionV1ChatSessionsSessionIdDeleteResponse400 | DeleteSessionV1ChatSessionsSessionIdDeleteResponse404 | DeleteSessionV1ChatSessionsSessionIdDeleteResponse426 | DeleteSessionV1ChatSessionsSessionIdDeleteResponse500 | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        session_id=session_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    session_id: str,
    *,
    client: AuthenticatedClient,
) -> (
    Any
    | DeleteSessionV1ChatSessionsSessionIdDeleteResponse400
    | DeleteSessionV1ChatSessionsSessionIdDeleteResponse404
    | DeleteSessionV1ChatSessionsSessionIdDeleteResponse426
    | DeleteSessionV1ChatSessionsSessionIdDeleteResponse500
    | HTTPValidationError
    | None
):
    """Delete Session

    Args:
        session_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | DeleteSessionV1ChatSessionsSessionIdDeleteResponse400 | DeleteSessionV1ChatSessionsSessionIdDeleteResponse404 | DeleteSessionV1ChatSessionsSessionIdDeleteResponse426 | DeleteSessionV1ChatSessionsSessionIdDeleteResponse500 | HTTPValidationError
    """

    return sync_detailed(
        session_id=session_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    session_id: str,
    *,
    client: AuthenticatedClient,
) -> Response[
    Any
    | DeleteSessionV1ChatSessionsSessionIdDeleteResponse400
    | DeleteSessionV1ChatSessionsSessionIdDeleteResponse404
    | DeleteSessionV1ChatSessionsSessionIdDeleteResponse426
    | DeleteSessionV1ChatSessionsSessionIdDeleteResponse500
    | HTTPValidationError
]:
    """Delete Session

    Args:
        session_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | DeleteSessionV1ChatSessionsSessionIdDeleteResponse400 | DeleteSessionV1ChatSessionsSessionIdDeleteResponse404 | DeleteSessionV1ChatSessionsSessionIdDeleteResponse426 | DeleteSessionV1ChatSessionsSessionIdDeleteResponse500 | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        session_id=session_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    session_id: str,
    *,
    client: AuthenticatedClient,
) -> (
    Any
    | DeleteSessionV1ChatSessionsSessionIdDeleteResponse400
    | DeleteSessionV1ChatSessionsSessionIdDeleteResponse404
    | DeleteSessionV1ChatSessionsSessionIdDeleteResponse426
    | DeleteSessionV1ChatSessionsSessionIdDeleteResponse500
    | HTTPValidationError
    | None
):
    """Delete Session

    Args:
        session_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | DeleteSessionV1ChatSessionsSessionIdDeleteResponse400 | DeleteSessionV1ChatSessionsSessionIdDeleteResponse404 | DeleteSessionV1ChatSessionsSessionIdDeleteResponse426 | DeleteSessionV1ChatSessionsSessionIdDeleteResponse500 | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            session_id=session_id,
            client=client,
        )
    ).parsed
