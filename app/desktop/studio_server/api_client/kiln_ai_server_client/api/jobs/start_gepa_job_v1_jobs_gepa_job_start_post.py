from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.body_start_gepa_job_v1_jobs_gepa_job_start_post import BodyStartGepaJobV1JobsGepaJobStartPost
from ...models.http_validation_error import HTTPValidationError
from ...models.job_start_response import JobStartResponse
from ...types import Response


def _get_kwargs(
    *,
    body: BodyStartGepaJobV1JobsGepaJobStartPost,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/v1/jobs/gepa_job/start",
    }

    _kwargs["files"] = body.to_multipart()

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | JobStartResponse | None:
    if response.status_code == 200:
        response_200 = JobStartResponse.from_dict(response.json())

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
) -> Response[HTTPValidationError | JobStartResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    body: BodyStartGepaJobV1JobsGepaJobStartPost,
) -> Response[HTTPValidationError | JobStartResponse]:
    """Start Gepa Job

    Args:
        body (BodyStartGepaJobV1JobsGepaJobStartPost):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | JobStartResponse]
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
    body: BodyStartGepaJobV1JobsGepaJobStartPost,
) -> HTTPValidationError | JobStartResponse | None:
    """Start Gepa Job

    Args:
        body (BodyStartGepaJobV1JobsGepaJobStartPost):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | JobStartResponse
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: BodyStartGepaJobV1JobsGepaJobStartPost,
) -> Response[HTTPValidationError | JobStartResponse]:
    """Start Gepa Job

    Args:
        body (BodyStartGepaJobV1JobsGepaJobStartPost):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | JobStartResponse]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    body: BodyStartGepaJobV1JobsGepaJobStartPost,
) -> HTTPValidationError | JobStartResponse | None:
    """Start Gepa Job

    Args:
        body (BodyStartGepaJobV1JobsGepaJobStartPost):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | JobStartResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
