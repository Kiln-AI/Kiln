"""Kiln API Call Tool - makes HTTP requests to the Kiln API server."""

import json
from typing import Any
from urllib.parse import unquote

import httpx
import jq

from kiln_ai.datamodel.tool_id import KilnBuiltInToolId
from kiln_ai.tools.base_tool import KilnTool, ToolCallContext, ToolCallResult

# httpx read timeout is per-read (idle), not a wall-clock cap: it resets every
# time a chunk arrives. So this bounds the gap *between* reads, not total
# request duration. For SSE that's the gap between events; for regular
# responses it's the gap between body chunks. A multi-hour eval that streams
# progress regularly never trips it — only this long of total silence does.
# Kiln's SSE endpoints are chatty (and emit keepalive pings), so a low bound is
# safe for them while still letting a genuinely stalled request fail reasonably
# fast.
READ_TIMEOUT_SECONDS = 900.0
# Short connection/setup timeout — server should accept quickly even when the
# body will then stream for a long time.
CONNECT_TIMEOUT_SECONDS = 30.0

# The base URL is the server root, and that server also hosts the web app and
# FastAPI's own doc routes. So a mistyped path does not 404 as JSON — it returns
# a web page, and thousands of tokens of HTML land in the model's context. Every
# Kiln API route lives under /api/ apart from /ping, so hold the tool to that.
API_PATH_PREFIX = "/api/"
ALLOWED_EXACT_PATHS = frozenset({"/ping"})
# Paths that a "did you mean /api<path>?" hint would only mislead on.
_NON_API_PATHS = frozenset({"/", "/docs", "/redoc", "/scalar"})


class KilnApiCallTool(KilnTool):
    """Tool for making HTTP requests to the Kiln API server."""

    def __init__(self, api_base_url: str):
        self._api_base_url = api_base_url
        super().__init__(
            tool_id=KilnBuiltInToolId.CALL_KILN_API,
            name="call_kiln_api",
            description=self._build_description(),
            parameters_schema=self._build_parameters_schema(),
        )

    @staticmethod
    def _build_description() -> str:
        return """Call the Kiln REST API. Makes an HTTP request and returns JSON with status_code and body.

Endpoint paths, request schemas, response fields, and jq filters are defined in per-endpoint documentation — not here. Load the endpoint doc before calling.

For SSE endpoints (text/event-stream), the tool consumes the stream until it closes (or a `data: complete` sentinel) and returns body = {"event_count": N, "message": str}. The stream ending does not mean the underlying job succeeded — check the flow's status afterward. Individual event payloads are not returned."""

    @staticmethod
    def _build_parameters_schema() -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "method": {
                    "type": "string",
                    "enum": ["GET", "POST", "PATCH", "DELETE"],
                    "description": "HTTP method for the API call",
                },
                "url_path": {
                    "type": "string",
                    "description": "API path with no query string — pass query args via query_params. Correct paths are in the endpoint documentation.",
                },
                "query_params": {
                    "type": "object",
                    "description": "Query string params. Values are strings or arrays of strings (arrays become repeated keys, e.g. ?ids=a&ids=b). Required and optional params are listed in the endpoint doc.",
                    "additionalProperties": {
                        "anyOf": [
                            {"type": "string"},
                            {"type": "array", "items": {"type": "string"}},
                        ],
                    },
                },
                "body": {
                    "description": "Request body for POST/PATCH. JSON string, object, or array — auto-serialized. Schema is in the endpoint doc.",
                },
                "jq_filter": {
                    "type": "string",
                    "description": "Optional jq expression applied to successful (2xx) responses.",
                },
            },
            "required": ["method", "url_path"],
        }

    async def run(  # type: ignore[override]
        self,
        context: ToolCallContext | None = None,
        *,
        method: str,
        url_path: str,
        body: str | dict | list | None = None,
        query_params: dict[str, str | list[str]] | None = None,
        jq_filter: str | None = None,
    ) -> ToolCallResult:
        body_str: str | None = None
        if isinstance(body, (dict, list)):
            body_str = json.dumps(body, ensure_ascii=False)
        elif isinstance(body, str):
            body_str = body

        # 1. Validate inputs
        method = method.upper()
        allowed_methods = {"GET", "POST", "PATCH", "DELETE"}
        if method not in allowed_methods:
            raise ValueError(
                f"Invalid method '{method}'. Must be one of: {', '.join(sorted(allowed_methods))}"
            )

        if not url_path.startswith("/"):
            raise ValueError(f"url_path must start with '/', got: {url_path}")

        if not _is_allowed_path(url_path):
            raise ValueError(_disallowed_path_message(url_path))

        if "?" in url_path or "#" in url_path:
            raise ValueError(
                "url_path must not contain a query string or fragment ('?' or '#'). "
                "Pass query args via query_params."
            )

        if body_str is not None and method in {"GET", "DELETE"}:
            raise ValueError(f"body parameter not allowed with {method} method")

        # 2. Build full URL
        full_url = f"{self._api_base_url}{url_path}"

        # 3. Make HTTP request — use stream() so we can detect SSE responses
        # from the content-type header and drain the event stream. The same
        # timeout applies to SSE and non-SSE responses: read is per-read (idle),
        # so it bounds silence on the channel rather than total duration.
        headers = {"Content-Type": "application/json"}
        # Per-request client: tool instances are short-lived (created per call
        # via tool_from_id), so a shared client wouldn't persist across calls anyway.
        timeout = httpx.Timeout(
            connect=CONNECT_TIMEOUT_SECONDS,
            read=READ_TIMEOUT_SECONDS,
            write=CONNECT_TIMEOUT_SECONDS,
            pool=CONNECT_TIMEOUT_SECONDS,
        )

        stream_kwargs: dict[str, Any] = {
            "headers": headers,
            "params": query_params,
            "timeout": timeout,
        }
        if method in {"POST", "PATCH"}:
            stream_kwargs["content"] = body_str

        async with httpx.AsyncClient() as client:
            try:
                async with client.stream(method, full_url, **stream_kwargs) as response:
                    status_code = response.status_code
                    content_type = response.headers.get("content-type", "").lower()
                    is_sse = content_type.startswith("text/event-stream")

                    if is_sse:
                        event_count = await _consume_sse(response)
                        response_text = json.dumps(
                            {
                                "event_count": event_count,
                                "message": "Stream finished. This does not guarantee the job completed successfully—check the status of the flow you triggered. For Eval or RAG runs, call this again if errors occur; transient failures may be retried. If errors keep happening, we advise running the flow through the web UI instead.",
                            },
                            ensure_ascii=False,
                        )
                    else:
                        raw = await response.aread()
                        response_text = raw.decode("utf-8", errors="replace")
            except httpx.TimeoutException as e:
                # Read timeouts use the read bound; connect/write/pool use the
                # connect one. Report whichever actually fired.
                if isinstance(e, httpx.ReadTimeout):
                    timeout_seconds = READ_TIMEOUT_SECONDS
                else:
                    timeout_seconds = CONNECT_TIMEOUT_SECONDS
                raise TimeoutError(
                    f"Request to {url_path} timed out after {timeout_seconds}s"
                )
            except httpx.ConnectError:
                raise ConnectionError(f"Could not connect to server for {url_path}")

        # 4. Build response
        if jq_filter and 200 <= status_code < 300:
            # Apply jq filter on successful responses
            try:
                parsed_json = json.loads(response_text)
            except json.JSONDecodeError as e:
                raise ValueError(f"Response is not valid JSON: {e}")

            try:
                compiled = jq.compile(jq_filter)
                filtered = compiled.input_value(parsed_json).text()
                response_body = filtered if filtered is not None else ""
            except Exception as e:
                raise ValueError(f"jq filter error: {e}")
        else:
            # Return raw body for non-2xx or when no filter
            response_body = response_text

        if isinstance(response_body, str):
            try:
                response_body = json.loads(response_body)
            except json.JSONDecodeError:
                pass

        result = {"status_code": status_code, "body": response_body}
        return ToolCallResult(output=json.dumps(result, ensure_ascii=False))


def _path_without_query(url_path: str) -> str:
    """The path portion alone.

    The query string is ignored by the path checks: a url_path carrying one is
    rejected by its own check, and stripping it first keeps those errors about
    the path.
    """
    return url_path.split("?", 1)[0].split("#", 1)[0]


def _has_dot_segment(path_only: str) -> bool:
    """True when any segment is '.' or '..', encoded or not.

    A prefix check alone is not enough, because the string we validate is not
    the path that gets sent. httpx resolves dot segments, so '/api/../docs'
    leaves as '/docs' and '/api/a/../../openapi.json' leaves as
    '/openapi.json' — both past a guard that only looked at the '/api/' at the
    front.

    Segments are decoded one at a time rather than decoding the whole path,
    then split again on any slash the decoding revealed. That catches an
    encoded '%2e%2e', and an encoded slash used to hide one ('%2e%2e%2f'),
    without treating an encoded slash as a separator in its own right — httpx
    leaves those encoded, so '/api/x%2Fy' is one segment and stays under
    '/api/'.
    """
    return any(
        part in {".", ".."}
        for segment in path_only.split("/")
        for part in unquote(segment).split("/")
    )


def _is_allowed_path(url_path: str) -> bool:
    """True when url_path addresses the Kiln REST API rather than the web app."""
    path_only = _path_without_query(url_path)
    if _has_dot_segment(path_only):
        return False
    return path_only in ALLOWED_EXACT_PATHS or path_only.startswith(API_PATH_PREFIX)


def _disallowed_path_message(url_path: str) -> str:
    path_only = _path_without_query(url_path)
    if _has_dot_segment(path_only):
        # A separate message: "must start with /api/" reads as nonsense for a
        # path that plainly does start with it.
        return (
            "url_path must not contain '.' or '..' path segments, encoded or "
            f"not — they resolve elsewhere before the request is sent. Got: "
            f"'{url_path}'. Write the full path. Correct paths are in the "
            "endpoint documentation."
        )

    # Suggest the prefixed form only where it could plausibly be the fix. A
    # dot in the final segment means a filename, not an endpoint, and
    # "/api/openapi.json" is no more callable than "/openapi.json".
    looks_like_a_file = "." in path_only.rsplit("/", 1)[-1]
    suggest = (
        not path_only.startswith("/api")
        and path_only not in _NON_API_PATHS
        and not looks_like_a_file
    )
    hint = f" Did you mean '/api{path_only}'?" if suggest else ""
    return (
        f"url_path must start with '{API_PATH_PREFIX}'. Got: '{url_path}'."
        f"{hint} Correct paths are in the endpoint documentation."
    )


async def _consume_sse(response: httpx.Response) -> int:
    """Drain an SSE response, returning the number of events seen.

    We count events but don't keep their payloads — a long stream (e.g. an eval
    run) can emit thousands, and the caller only needs to know it finished.
    A ``data: complete`` sentinel ends the stream and is not counted as an event.
    Draining blocks until the stream closes, so the tool call returns only once
    the underlying operation is done.
    """
    event_count = 0
    data_lines: list[str] = []

    async for line in response.aiter_lines():
        line = line.rstrip("\r")
        if line == "":
            if data_lines:
                payload = "\n".join(data_lines)
                data_lines = []
                if payload == "complete":
                    break
                event_count += 1
            continue
        if line.startswith(":"):
            # SSE comment — ignore
            continue
        if line.startswith("data:"):
            # SSE spec: strip exactly one leading space after "data:".
            data_lines.append(line[5:].removeprefix(" "))

    # Flush a trailing event if the stream closed without a final blank line.
    if data_lines and "\n".join(data_lines) != "complete":
        event_count += 1

    return event_count
