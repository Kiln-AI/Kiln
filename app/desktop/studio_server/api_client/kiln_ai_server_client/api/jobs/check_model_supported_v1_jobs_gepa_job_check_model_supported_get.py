from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.check_model_supported_response import CheckModelSupportedResponse
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response


def _get_kwargs(
    *,
    model_name: str,
    model_provider_name: str,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["model_name"] = model_name

    params["model_provider_name"] = model_provider_name

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/jobs/gepa_job/check_model_supported",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> CheckModelSupportedResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = CheckModelSupportedResponse.from_dict(response.json())

        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())

        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[CheckModelSupportedResponse | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    model_name: str,
    model_provider_name: str,
) -> Response[CheckModelSupportedResponse | HTTPValidationError]:
    """Check Model Supported

    Args:
        model_name (str):
        model_provider_name (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CheckModelSupportedResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        model_name=model_name,
        model_provider_name=model_provider_name,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    model_name: str,
    model_provider_name: str,
) -> CheckModelSupportedResponse | HTTPValidationError | None:
    """Check Model Supported

    Args:
        model_name (str):
        model_provider_name (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CheckModelSupportedResponse | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        model_name=model_name,
        model_provider_name=model_provider_name,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    model_name: str,
    model_provider_name: str,
) -> Response[CheckModelSupportedResponse | HTTPValidationError]:
    """Check Model Supported

    Args:
        model_name (str):
        model_provider_name (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CheckModelSupportedResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        model_name=model_name,
        model_provider_name=model_provider_name,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    model_name: str,
    model_provider_name: str,
) -> CheckModelSupportedResponse | HTTPValidationError | None:
    """Check Model Supported

    Args:
        model_name (str):
        model_provider_name (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CheckModelSupportedResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            model_name=model_name,
            model_provider_name=model_provider_name,
        )
    ).parsed
