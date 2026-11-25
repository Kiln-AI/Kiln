"""The steps of one `call_kiln_api` call, from the agent's arguments to the
tool result."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

import httpx
from kiln_ai.tools.built_in_tools import (
    KilnApiCallTool,
    KilnApiResponse,
    KilnApiResponseError,
    prepare_api_request,
)
from mcp.types import CallToolResult, TextContent
from starlette.requests import Request

from kiln_mcp_server.api_tool import messages
from kiln_mcp_server.api_tool.policy import ApiCall
from kiln_mcp_server.api_tool.progress import ProgressSender, run_with_progress
from kiln_mcp_server.api_tool.tmp_files import TmpFileError

if TYPE_CHECKING:
    from kiln_mcp_server.api_tool.tool import ApiToolDeps

logger = logging.getLogger(__name__)

QueryValue = str | int | float | bool
QueryParams = Mapping[str, QueryValue | None | list[QueryValue]]


def coerce_query_params(
    query_params: QueryParams | None,
) -> dict[str, str | list[str]] | None:
    """Query values as the strings to send. A `None` value drops its key, and a
    list repeats it. An empty result is `None`."""
    if not query_params:
        return None
    coerced: dict[str, str | list[str]] = {}
    for key, value in query_params.items():
        if value is None:
            continue
        if isinstance(value, list):
            coerced[key] = [_query_string(item) for item in value]
        else:
            coerced[key] = _query_string(value)
    return coerced or None


def _query_string(value: QueryValue) -> str:
    # bool is a subclass of int, so it is tested first.
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else repr(value)
    return value


def _compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _text_result(text: str, *, is_error: bool) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=text)], isError=is_error
    )


def _error(text: str) -> CallToolResult:
    return _text_result(text, is_error=True)


async def run_api_call(
    deps: ApiToolDeps,
    request: Request | None,
    send_progress: ProgressSender | None,
    *,
    method: str,
    url_path: str,
    body: dict | list | str | None,
    query_params: QueryParams | None,
    jq_filter: str | None,
    body_limit: int,
    save_to_tmpfile: bool,
) -> CallToolResult:
    """Run one call. Every refusal and failure is returned as an error result
    with a text for the agent; a non-2xx API answer is returned as data."""
    if body_limit < 1:
        return _error(messages.bad_body_limit(body_limit))

    try:
        prepared = prepare_api_request(method, url_path, body)
    except ValueError as e:
        return _error(str(e))
    method, url_path = prepared.method, prepared.url_path

    match = deps.route_index.match(method, url_path)
    if match.kind == "wrong_method":
        logger.debug("call_kiln_api refused, wrong method: %s %s", method, url_path)
        return _error(messages.wrong_method(method, url_path, match.path_methods))
    route = match.entry
    if route is None:
        logger.debug("call_kiln_api refused, unknown endpoint: %s %s", method, url_path)
        return _error(messages.unknown_endpoint(method, url_path))

    params = coerce_query_params(query_params)

    scope = deps.policy.scope_for_request(request)
    decision = deps.policy.check(
        ApiCall(
            method=method,
            url_path=url_path,
            route=route,
            path_params=match.path_params,
            query_params=params,
            body=prepared.body_str,
        ),
        scope,
    )
    if not decision.allowed:
        logger.debug("call_kiln_api refused by policy: %s %s", method, url_path)
        return _error(decision.message or messages.blocked_endpoint(method, route.path))

    tool = KilnApiCallTool(deps.api_base_url, deps.transport)
    try:
        response = await run_with_progress(
            tool.call(
                method=method,
                url_path=url_path,
                body=prepared.body_str,
                query_params=params,
                jq_filter=jq_filter,
            ),
            send_progress,
            label=f"{method} {url_path}",
            interval=deps.progress_interval,
        )
    except (TimeoutError, ConnectionError) as e:
        return _error(messages.request_failed(str(e), method))
    # The core tool converts only timeouts and refused connections. Any other
    # transport failure, such as a stream cut part-way, can also follow a request
    # the server already acted on.
    except httpx.TransportError as e:
        return _error(
            messages.request_failed(
                f"Request to {url_path} failed: {type(e).__name__}", method
            )
        )
    except KilnApiResponseError as e:
        return _error(messages.response_unusable(str(e), method, e.status_code))
    except Exception as e:
        logger.exception("call_kiln_api failed: %s %s", method, url_path)
        return _error(messages.unexpected_error(e))

    return await asyncio.to_thread(
        _shape_result, deps, response, method, body_limit, save_to_tmpfile
    )


def _shape_result(
    deps: ApiToolDeps,
    response: KilnApiResponse,
    method: str,
    body_limit: int,
    save_to_tmpfile: bool,
) -> CallToolResult:
    is_2xx = 200 <= response.status_code < 300
    # The agent needs an API error in full, so a non-2xx is never saved or cut.
    if is_2xx and save_to_tmpfile:
        try:
            saved = deps.tmp_files.save(response.body_text, response.body_is_json)
        except (TmpFileError, OSError) as e:
            return _error(messages.save_failed(str(e), method, response.status_code))
        return _text_result(
            _compact_json(
                {
                    "status_code": response.status_code,
                    "body_path": str(saved.path),
                    "size_bytes": saved.size_bytes,
                }
            ),
            is_error=False,
        )
    body_json = _compact_json(response.body)
    # A POST, PATCH or DELETE has already done its work; refusing its body
    # would invite a retry that repeats it.
    if is_2xx and method == "GET" and len(body_json) > body_limit:
        return _error(messages.body_too_long(len(body_json), body_limit))
    return _text_result(
        f'{{"status_code":{response.status_code},"body":{body_json}}}',
        is_error=False,
    )
