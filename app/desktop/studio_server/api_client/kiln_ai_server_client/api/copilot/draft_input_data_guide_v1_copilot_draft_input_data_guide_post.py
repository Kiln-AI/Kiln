from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.draft_input_data_guide_input import DraftInputDataGuideInput
from ...models.draft_input_data_guide_output import DraftInputDataGuideOutput
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    *,
    body: DraftInputDataGuideInput,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/v1/copilot/draft_input_data_guide",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> DraftInputDataGuideOutput | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = DraftInputDataGuideOutput.from_dict(response.json())

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
) -> Response[DraftInputDataGuideOutput | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    body: DraftInputDataGuideInput,
) -> Response[DraftInputDataGuideOutput | HTTPValidationError]:
    """Draft Input Data Guide

     Draft an input data guide from a heterogeneous list of input examples
    (manual entries, selected task runs, uploaded text documents) describing
    what realistic inputs to the task look like.

    Args:
        body (DraftInputDataGuideInput): Request payload for the draft step of the Input Data
            Guide copilot.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DraftInputDataGuideOutput | HTTPValidationError]
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
    body: DraftInputDataGuideInput,
) -> DraftInputDataGuideOutput | HTTPValidationError | None:
    """Draft Input Data Guide

     Draft an input data guide from a heterogeneous list of input examples
    (manual entries, selected task runs, uploaded text documents) describing
    what realistic inputs to the task look like.

    Args:
        body (DraftInputDataGuideInput): Request payload for the draft step of the Input Data
            Guide copilot.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DraftInputDataGuideOutput | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: DraftInputDataGuideInput,
) -> Response[DraftInputDataGuideOutput | HTTPValidationError]:
    """Draft Input Data Guide

     Draft an input data guide from a heterogeneous list of input examples
    (manual entries, selected task runs, uploaded text documents) describing
    what realistic inputs to the task look like.

    Args:
        body (DraftInputDataGuideInput): Request payload for the draft step of the Input Data
            Guide copilot.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DraftInputDataGuideOutput | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    body: DraftInputDataGuideInput,
) -> DraftInputDataGuideOutput | HTTPValidationError | None:
    """Draft Input Data Guide

     Draft an input data guide from a heterogeneous list of input examples
    (manual entries, selected task runs, uploaded text documents) describing
    what realistic inputs to the task look like.

    Args:
        body (DraftInputDataGuideInput): Request payload for the draft step of the Input Data
            Guide copilot.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DraftInputDataGuideOutput | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
