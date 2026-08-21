from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.client_version_policy import ClientVersionPolicy
from ...types import Response


def _get_kwargs() -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/chat/version_policy",
    }

    return _kwargs


def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> ClientVersionPolicy | None:
    if response.status_code == 200:
        response_200 = ClientVersionPolicy.from_dict(response.json())

        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[ClientVersionPolicy]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
) -> Response[ClientVersionPolicy]:
    """Get Client Version Policy

     Report the version verdict for this client without rejecting it.

    Lets the client surface the upgrade banners on load (before sending a
    message) without itself triggering the 426 gate. Deliberately does not call
    ``_enforce_client_version`` so a too-old client can still learn it's too old.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ClientVersionPolicy]
    """

    kwargs = _get_kwargs()

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
) -> ClientVersionPolicy | None:
    """Get Client Version Policy

     Report the version verdict for this client without rejecting it.

    Lets the client surface the upgrade banners on load (before sending a
    message) without itself triggering the 426 gate. Deliberately does not call
    ``_enforce_client_version`` so a too-old client can still learn it's too old.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ClientVersionPolicy
    """

    return sync_detailed(
        client=client,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
) -> Response[ClientVersionPolicy]:
    """Get Client Version Policy

     Report the version verdict for this client without rejecting it.

    Lets the client surface the upgrade banners on load (before sending a
    message) without itself triggering the 426 gate. Deliberately does not call
    ``_enforce_client_version`` so a too-old client can still learn it's too old.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ClientVersionPolicy]
    """

    kwargs = _get_kwargs()

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
) -> ClientVersionPolicy | None:
    """Get Client Version Policy

     Report the version verdict for this client without rejecting it.

    Lets the client surface the upgrade banners on load (before sending a
    message) without itself triggering the 426 gate. Deliberately does not call
    ``_enforce_client_version`` so a too-old client can still learn it's too old.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ClientVersionPolicy
    """

    return (
        await asyncio_detailed(
            client=client,
        )
    ).parsed
