from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.health_health_get_response_health_health_get import (
    HealthHealthGetResponseHealthHealthGet,
)
from ...types import Response


def _get_kwargs() -> dict[str, Any]:
    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/health",
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HealthHealthGetResponseHealthHealthGet | None:
    if response.status_code == 200:
        response_200 = HealthHealthGetResponseHealthHealthGet.from_dict(response.json())

        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[HealthHealthGetResponseHealthHealthGet]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
) -> Response[HealthHealthGetResponseHealthHealthGet]:
    r"""Health

     Health check endpoint.

    Returns the current health status of the service.

    Returns:
        dict: A dictionary containing the service status. {\"status\": \"ok\"} is expected.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HealthHealthGetResponseHealthHealthGet]
    """

    kwargs = _get_kwargs()

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
) -> HealthHealthGetResponseHealthHealthGet | None:
    r"""Health

     Health check endpoint.

    Returns the current health status of the service.

    Returns:
        dict: A dictionary containing the service status. {\"status\": \"ok\"} is expected.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HealthHealthGetResponseHealthHealthGet
    """

    return sync_detailed(
        client=client,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
) -> Response[HealthHealthGetResponseHealthHealthGet]:
    r"""Health

     Health check endpoint.

    Returns the current health status of the service.

    Returns:
        dict: A dictionary containing the service status. {\"status\": \"ok\"} is expected.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HealthHealthGetResponseHealthHealthGet]
    """

    kwargs = _get_kwargs()

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
) -> HealthHealthGetResponseHealthHealthGet | None:
    r"""Health

     Health check endpoint.

    Returns the current health status of the service.

    Returns:
        dict: A dictionary containing the service status. {\"status\": \"ok\"} is expected.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HealthHealthGetResponseHealthHealthGet
    """

    return (
        await asyncio_detailed(
            client=client,
        )
    ).parsed
