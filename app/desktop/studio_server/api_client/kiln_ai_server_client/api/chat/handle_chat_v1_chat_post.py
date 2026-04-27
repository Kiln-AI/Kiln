from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.chat_request import ChatRequest
from ...models.handle_chat_v1_chat_post_response_400 import HandleChatV1ChatPostResponse400
from ...models.handle_chat_v1_chat_post_response_404 import HandleChatV1ChatPostResponse404
from ...models.handle_chat_v1_chat_post_response_426 import HandleChatV1ChatPostResponse426
from ...models.handle_chat_v1_chat_post_response_500 import HandleChatV1ChatPostResponse500
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    *,
    body: ChatRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/v1/chat/",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> (
    Any
    | HTTPValidationError
    | HandleChatV1ChatPostResponse400
    | HandleChatV1ChatPostResponse404
    | HandleChatV1ChatPostResponse426
    | HandleChatV1ChatPostResponse500
    | None
):
    if response.status_code == 200:
        response_200 = response.json()
        return response_200

    if response.status_code == 400:
        response_400 = HandleChatV1ChatPostResponse400.from_dict(response.json())

        return response_400

    if response.status_code == 404:
        response_404 = HandleChatV1ChatPostResponse404.from_dict(response.json())

        return response_404

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())

        return response_422

    if response.status_code == 426:
        response_426 = HandleChatV1ChatPostResponse426.from_dict(response.json())

        return response_426

    if response.status_code == 500:
        response_500 = HandleChatV1ChatPostResponse500.from_dict(response.json())

        return response_500

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[
    Any
    | HTTPValidationError
    | HandleChatV1ChatPostResponse400
    | HandleChatV1ChatPostResponse404
    | HandleChatV1ChatPostResponse426
    | HandleChatV1ChatPostResponse500
]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    body: ChatRequest,
) -> Response[
    Any
    | HTTPValidationError
    | HandleChatV1ChatPostResponse400
    | HandleChatV1ChatPostResponse404
    | HandleChatV1ChatPostResponse426
    | HandleChatV1ChatPostResponse500
]:
    """Handle Chat

    Args:
        body (ChatRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | HandleChatV1ChatPostResponse400 | HandleChatV1ChatPostResponse404 | HandleChatV1ChatPostResponse426 | HandleChatV1ChatPostResponse500]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    body: ChatRequest,
) -> (
    Any
    | HTTPValidationError
    | HandleChatV1ChatPostResponse400
    | HandleChatV1ChatPostResponse404
    | HandleChatV1ChatPostResponse426
    | HandleChatV1ChatPostResponse500
    | None
):
    """Handle Chat

    Args:
        body (ChatRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | HandleChatV1ChatPostResponse400 | HandleChatV1ChatPostResponse404 | HandleChatV1ChatPostResponse426 | HandleChatV1ChatPostResponse500
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: ChatRequest,
) -> Response[
    Any
    | HTTPValidationError
    | HandleChatV1ChatPostResponse400
    | HandleChatV1ChatPostResponse404
    | HandleChatV1ChatPostResponse426
    | HandleChatV1ChatPostResponse500
]:
    """Handle Chat

    Args:
        body (ChatRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | HandleChatV1ChatPostResponse400 | HandleChatV1ChatPostResponse404 | HandleChatV1ChatPostResponse426 | HandleChatV1ChatPostResponse500]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    body: ChatRequest,
) -> (
    Any
    | HTTPValidationError
    | HandleChatV1ChatPostResponse400
    | HandleChatV1ChatPostResponse404
    | HandleChatV1ChatPostResponse426
    | HandleChatV1ChatPostResponse500
    | None
):
    """Handle Chat

    Args:
        body (ChatRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | HandleChatV1ChatPostResponse400 | HandleChatV1ChatPostResponse404 | HandleChatV1ChatPostResponse426 | HandleChatV1ChatPostResponse500
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
