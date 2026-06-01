from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.generate_synthetic_users_request import GenerateSyntheticUsersRequest
from ...models.generate_synthetic_users_response import GenerateSyntheticUsersResponse
from ...models.generate_v1_synthetic_user_generate_post_response_401 import (
    GenerateV1SyntheticUserGeneratePostResponse401,
)
from ...models.generate_v1_synthetic_user_generate_post_response_500 import (
    GenerateV1SyntheticUserGeneratePostResponse500,
)
from ...models.generate_v1_synthetic_user_generate_post_response_502 import (
    GenerateV1SyntheticUserGeneratePostResponse502,
)
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    *,
    body: GenerateSyntheticUsersRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/v1/synthetic_user/generate",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> (
    GenerateSyntheticUsersResponse
    | GenerateV1SyntheticUserGeneratePostResponse401
    | GenerateV1SyntheticUserGeneratePostResponse500
    | GenerateV1SyntheticUserGeneratePostResponse502
    | HTTPValidationError
    | None
):
    if response.status_code == 200:
        response_200 = GenerateSyntheticUsersResponse.from_dict(response.json())

        return response_200

    if response.status_code == 401:
        response_401 = GenerateV1SyntheticUserGeneratePostResponse401.from_dict(response.json())

        return response_401

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())

        return response_422

    if response.status_code == 500:
        response_500 = GenerateV1SyntheticUserGeneratePostResponse500.from_dict(response.json())

        return response_500

    if response.status_code == 502:
        response_502 = GenerateV1SyntheticUserGeneratePostResponse502.from_dict(response.json())

        return response_502

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[
    GenerateSyntheticUsersResponse
    | GenerateV1SyntheticUserGeneratePostResponse401
    | GenerateV1SyntheticUserGeneratePostResponse500
    | GenerateV1SyntheticUserGeneratePostResponse502
    | HTTPValidationError
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
    body: GenerateSyntheticUsersRequest,
) -> Response[
    GenerateSyntheticUsersResponse
    | GenerateV1SyntheticUserGeneratePostResponse401
    | GenerateV1SyntheticUserGeneratePostResponse500
    | GenerateV1SyntheticUserGeneratePostResponse502
    | HTTPValidationError
]:
    """Generate

     Return `num_cases` synthetic-user cases for the authoring UX.

    Args:
        body (GenerateSyntheticUsersRequest): Request body for POST /v1/synthetic_user/generate.

            Generates `num_cases` synthetic-user cases designed to probe
            `target_specification` against the agent described by `target_task_prompt`,
            across multi-turn conversations.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[GenerateSyntheticUsersResponse | GenerateV1SyntheticUserGeneratePostResponse401 | GenerateV1SyntheticUserGeneratePostResponse500 | GenerateV1SyntheticUserGeneratePostResponse502 | HTTPValidationError]
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
    body: GenerateSyntheticUsersRequest,
) -> (
    GenerateSyntheticUsersResponse
    | GenerateV1SyntheticUserGeneratePostResponse401
    | GenerateV1SyntheticUserGeneratePostResponse500
    | GenerateV1SyntheticUserGeneratePostResponse502
    | HTTPValidationError
    | None
):
    """Generate

     Return `num_cases` synthetic-user cases for the authoring UX.

    Args:
        body (GenerateSyntheticUsersRequest): Request body for POST /v1/synthetic_user/generate.

            Generates `num_cases` synthetic-user cases designed to probe
            `target_specification` against the agent described by `target_task_prompt`,
            across multi-turn conversations.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        GenerateSyntheticUsersResponse | GenerateV1SyntheticUserGeneratePostResponse401 | GenerateV1SyntheticUserGeneratePostResponse500 | GenerateV1SyntheticUserGeneratePostResponse502 | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: GenerateSyntheticUsersRequest,
) -> Response[
    GenerateSyntheticUsersResponse
    | GenerateV1SyntheticUserGeneratePostResponse401
    | GenerateV1SyntheticUserGeneratePostResponse500
    | GenerateV1SyntheticUserGeneratePostResponse502
    | HTTPValidationError
]:
    """Generate

     Return `num_cases` synthetic-user cases for the authoring UX.

    Args:
        body (GenerateSyntheticUsersRequest): Request body for POST /v1/synthetic_user/generate.

            Generates `num_cases` synthetic-user cases designed to probe
            `target_specification` against the agent described by `target_task_prompt`,
            across multi-turn conversations.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[GenerateSyntheticUsersResponse | GenerateV1SyntheticUserGeneratePostResponse401 | GenerateV1SyntheticUserGeneratePostResponse500 | GenerateV1SyntheticUserGeneratePostResponse502 | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    body: GenerateSyntheticUsersRequest,
) -> (
    GenerateSyntheticUsersResponse
    | GenerateV1SyntheticUserGeneratePostResponse401
    | GenerateV1SyntheticUserGeneratePostResponse500
    | GenerateV1SyntheticUserGeneratePostResponse502
    | HTTPValidationError
    | None
):
    """Generate

     Return `num_cases` synthetic-user cases for the authoring UX.

    Args:
        body (GenerateSyntheticUsersRequest): Request body for POST /v1/synthetic_user/generate.

            Generates `num_cases` synthetic-user cases designed to probe
            `target_specification` against the agent described by `target_task_prompt`,
            across multi-turn conversations.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        GenerateSyntheticUsersResponse | GenerateV1SyntheticUserGeneratePostResponse401 | GenerateV1SyntheticUserGeneratePostResponse500 | GenerateV1SyntheticUserGeneratePostResponse502 | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
