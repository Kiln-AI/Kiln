from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.chat_snapshot import ChatSnapshot
from ...models.get_session_v1_chat_sessions_session_id_get_response_400 import (
    GetSessionV1ChatSessionsSessionIdGetResponse400,
)
from ...models.get_session_v1_chat_sessions_session_id_get_response_404 import (
    GetSessionV1ChatSessionsSessionIdGetResponse404,
)
from ...models.get_session_v1_chat_sessions_session_id_get_response_426 import (
    GetSessionV1ChatSessionsSessionIdGetResponse426,
)
from ...models.get_session_v1_chat_sessions_session_id_get_response_500 import (
    GetSessionV1ChatSessionsSessionIdGetResponse500,
)
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    session_id: str,
) -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/chat/sessions/{session_id}".format(
            session_id=quote(str(session_id), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> (
    ChatSnapshot
    | GetSessionV1ChatSessionsSessionIdGetResponse400
    | GetSessionV1ChatSessionsSessionIdGetResponse404
    | GetSessionV1ChatSessionsSessionIdGetResponse426
    | GetSessionV1ChatSessionsSessionIdGetResponse500
    | HTTPValidationError
    | None
):
    if response.status_code == 200:
        response_200 = ChatSnapshot.from_dict(response.json())

        return response_200

    if response.status_code == 400:
        response_400 = GetSessionV1ChatSessionsSessionIdGetResponse400.from_dict(response.json())

        return response_400

    if response.status_code == 404:
        response_404 = GetSessionV1ChatSessionsSessionIdGetResponse404.from_dict(response.json())

        return response_404

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())

        return response_422

    if response.status_code == 426:
        response_426 = GetSessionV1ChatSessionsSessionIdGetResponse426.from_dict(response.json())

        return response_426

    if response.status_code == 500:
        response_500 = GetSessionV1ChatSessionsSessionIdGetResponse500.from_dict(response.json())

        return response_500

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[
    ChatSnapshot
    | GetSessionV1ChatSessionsSessionIdGetResponse400
    | GetSessionV1ChatSessionsSessionIdGetResponse404
    | GetSessionV1ChatSessionsSessionIdGetResponse426
    | GetSessionV1ChatSessionsSessionIdGetResponse500
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
    ChatSnapshot
    | GetSessionV1ChatSessionsSessionIdGetResponse400
    | GetSessionV1ChatSessionsSessionIdGetResponse404
    | GetSessionV1ChatSessionsSessionIdGetResponse426
    | GetSessionV1ChatSessionsSessionIdGetResponse500
    | HTTPValidationError
]:
    """Get Session

    Args:
        session_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ChatSnapshot | GetSessionV1ChatSessionsSessionIdGetResponse400 | GetSessionV1ChatSessionsSessionIdGetResponse404 | GetSessionV1ChatSessionsSessionIdGetResponse426 | GetSessionV1ChatSessionsSessionIdGetResponse500 | HTTPValidationError]
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
    ChatSnapshot
    | GetSessionV1ChatSessionsSessionIdGetResponse400
    | GetSessionV1ChatSessionsSessionIdGetResponse404
    | GetSessionV1ChatSessionsSessionIdGetResponse426
    | GetSessionV1ChatSessionsSessionIdGetResponse500
    | HTTPValidationError
    | None
):
    """Get Session

    Args:
        session_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ChatSnapshot | GetSessionV1ChatSessionsSessionIdGetResponse400 | GetSessionV1ChatSessionsSessionIdGetResponse404 | GetSessionV1ChatSessionsSessionIdGetResponse426 | GetSessionV1ChatSessionsSessionIdGetResponse500 | HTTPValidationError
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
    ChatSnapshot
    | GetSessionV1ChatSessionsSessionIdGetResponse400
    | GetSessionV1ChatSessionsSessionIdGetResponse404
    | GetSessionV1ChatSessionsSessionIdGetResponse426
    | GetSessionV1ChatSessionsSessionIdGetResponse500
    | HTTPValidationError
]:
    """Get Session

    Args:
        session_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ChatSnapshot | GetSessionV1ChatSessionsSessionIdGetResponse400 | GetSessionV1ChatSessionsSessionIdGetResponse404 | GetSessionV1ChatSessionsSessionIdGetResponse426 | GetSessionV1ChatSessionsSessionIdGetResponse500 | HTTPValidationError]
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
    ChatSnapshot
    | GetSessionV1ChatSessionsSessionIdGetResponse400
    | GetSessionV1ChatSessionsSessionIdGetResponse404
    | GetSessionV1ChatSessionsSessionIdGetResponse426
    | GetSessionV1ChatSessionsSessionIdGetResponse500
    | HTTPValidationError
    | None
):
    """Get Session

    Args:
        session_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ChatSnapshot | GetSessionV1ChatSessionsSessionIdGetResponse400 | GetSessionV1ChatSessionsSessionIdGetResponse404 | GetSessionV1ChatSessionsSessionIdGetResponse426 | GetSessionV1ChatSessionsSessionIdGetResponse500 | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            session_id=session_id,
            client=client,
        )
    ).parsed
