from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.check_entitlements_v1_check_entitlements_get_response_check_entitlements_v1_check_entitlements_get import (
    CheckEntitlementsV1CheckEntitlementsGetResponseCheckEntitlementsV1CheckEntitlementsGet,
)
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response


def _get_kwargs(
    *,
    feature_codes: str,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["feature_codes"] = feature_codes

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/check_entitlements",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> (
    CheckEntitlementsV1CheckEntitlementsGetResponseCheckEntitlementsV1CheckEntitlementsGet | HTTPValidationError | None
):
    if response.status_code == 200:
        response_200 = CheckEntitlementsV1CheckEntitlementsGetResponseCheckEntitlementsV1CheckEntitlementsGet.from_dict(
            response.json()
        )

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
) -> Response[
    CheckEntitlementsV1CheckEntitlementsGetResponseCheckEntitlementsV1CheckEntitlementsGet | HTTPValidationError
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
    feature_codes: str,
) -> Response[
    CheckEntitlementsV1CheckEntitlementsGetResponseCheckEntitlementsV1CheckEntitlementsGet | HTTPValidationError
]:
    """Check Entitlements

     Check whether the authenticated user's organization has the given entitlement
    feature code(s). Pass as comma-separated string (e.g., 'code1,code2').
    Returns a JSON object with each feature code as key and true or false.

    Args:
        feature_codes (str): Comma-separated entitlement feature code(s) to check

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CheckEntitlementsV1CheckEntitlementsGetResponseCheckEntitlementsV1CheckEntitlementsGet | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        feature_codes=feature_codes,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    feature_codes: str,
) -> (
    CheckEntitlementsV1CheckEntitlementsGetResponseCheckEntitlementsV1CheckEntitlementsGet | HTTPValidationError | None
):
    """Check Entitlements

     Check whether the authenticated user's organization has the given entitlement
    feature code(s). Pass as comma-separated string (e.g., 'code1,code2').
    Returns a JSON object with each feature code as key and true or false.

    Args:
        feature_codes (str): Comma-separated entitlement feature code(s) to check

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CheckEntitlementsV1CheckEntitlementsGetResponseCheckEntitlementsV1CheckEntitlementsGet | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        feature_codes=feature_codes,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    feature_codes: str,
) -> Response[
    CheckEntitlementsV1CheckEntitlementsGetResponseCheckEntitlementsV1CheckEntitlementsGet | HTTPValidationError
]:
    """Check Entitlements

     Check whether the authenticated user's organization has the given entitlement
    feature code(s). Pass as comma-separated string (e.g., 'code1,code2').
    Returns a JSON object with each feature code as key and true or false.

    Args:
        feature_codes (str): Comma-separated entitlement feature code(s) to check

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CheckEntitlementsV1CheckEntitlementsGetResponseCheckEntitlementsV1CheckEntitlementsGet | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        feature_codes=feature_codes,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    feature_codes: str,
) -> (
    CheckEntitlementsV1CheckEntitlementsGetResponseCheckEntitlementsV1CheckEntitlementsGet | HTTPValidationError | None
):
    """Check Entitlements

     Check whether the authenticated user's organization has the given entitlement
    feature code(s). Pass as comma-separated string (e.g., 'code1,code2').
    Returns a JSON object with each feature code as key and true or false.

    Args:
        feature_codes (str): Comma-separated entitlement feature code(s) to check

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CheckEntitlementsV1CheckEntitlementsGetResponseCheckEntitlementsV1CheckEntitlementsGet | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            feature_codes=feature_codes,
        )
    ).parsed
