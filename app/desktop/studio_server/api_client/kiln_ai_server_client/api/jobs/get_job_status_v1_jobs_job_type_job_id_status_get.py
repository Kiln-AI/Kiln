from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.job_status_response import JobStatusResponse
from ...models.job_type import JobType
from ...types import Response


def _get_kwargs(
    job_type: JobType,
    job_id: str,
) -> dict[str, Any]:
    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/jobs/{job_type}/{job_id}/status".format(
            job_type=quote(str(job_type), safe=""),
            job_id=quote(str(job_id), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | JobStatusResponse | None:
    if response.status_code == 200:
        response_200 = JobStatusResponse.from_dict(response.json())

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
) -> Response[HTTPValidationError | JobStatusResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    job_type: JobType,
    job_id: str,
    *,
    client: AuthenticatedClient,
) -> Response[HTTPValidationError | JobStatusResponse]:
    """Get Job Status

     Get the status of a job.

    Args:
        job_type: The type of job
        job_id: The job ID

    Returns:
        The current job status

    Raises:
        HTTPException: If the job type is unknown

    Args:
        job_type (JobType):
        job_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | JobStatusResponse]
    """

    kwargs = _get_kwargs(
        job_type=job_type,
        job_id=job_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    job_type: JobType,
    job_id: str,
    *,
    client: AuthenticatedClient,
) -> HTTPValidationError | JobStatusResponse | None:
    """Get Job Status

     Get the status of a job.

    Args:
        job_type: The type of job
        job_id: The job ID

    Returns:
        The current job status

    Raises:
        HTTPException: If the job type is unknown

    Args:
        job_type (JobType):
        job_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | JobStatusResponse
    """

    return sync_detailed(
        job_type=job_type,
        job_id=job_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    job_type: JobType,
    job_id: str,
    *,
    client: AuthenticatedClient,
) -> Response[HTTPValidationError | JobStatusResponse]:
    """Get Job Status

     Get the status of a job.

    Args:
        job_type: The type of job
        job_id: The job ID

    Returns:
        The current job status

    Raises:
        HTTPException: If the job type is unknown

    Args:
        job_type (JobType):
        job_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | JobStatusResponse]
    """

    kwargs = _get_kwargs(
        job_type=job_type,
        job_id=job_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    job_type: JobType,
    job_id: str,
    *,
    client: AuthenticatedClient,
) -> HTTPValidationError | JobStatusResponse | None:
    """Get Job Status

     Get the status of a job.

    Args:
        job_type: The type of job
        job_id: The job ID

    Returns:
        The current job status

    Raises:
        HTTPException: If the job type is unknown

    Args:
        job_type (JobType):
        job_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | JobStatusResponse
    """

    return (
        await asyncio_detailed(
            job_type=job_type,
            job_id=job_id,
            client=client,
        )
    ).parsed
