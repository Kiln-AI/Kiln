"""Kiln API Call Tool - makes HTTP requests to the Kiln API server."""

import json
from typing import Any

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

For SSE endpoints (text/event-stream), the tool consumes the stream until it closes (or a `data: complete` sentinel) and returns body = {"event_count": N, "complete": bool}. Individual event payloads are not returned."""

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
                        event_count, complete = await _consume_sse(response)
                        response_text = json.dumps(
                            {
                                "event_count": event_count,
                                "complete": complete,
                            }
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


async def _consume_sse(response: httpx.Response) -> tuple[int, bool]:
    """Drain an SSE response, returning (event_count, complete).

    Event payloads are intentionally not retained — a long stream (e.g. an eval
    run) can emit thousands of events, and the caller only needs to know it
    finished, not replay every progress update. We count events and detect the
    explicit ``data: complete`` sentinel. ``complete`` is True only on that
    sentinel — a clean stream end does NOT set it. The sentinel is emitted by
    some Kiln endpoints (eval runs, RAG indexing) but not others (chat), so
    ``complete=False`` is normal for streams that don't use it and does not by
    itself imply truncation. Draining still blocks until the stream closes, so
    the tool call returns only once the underlying operation has finished.
    """
    event_count = 0
    data_lines: list[str] = []
    saw_complete_sentinel = False

    async for line in response.aiter_lines():
        line = line.rstrip("\r")
        if line == "":
            if data_lines:
                payload = "\n".join(data_lines)
                data_lines = []
                if payload == "complete":
                    saw_complete_sentinel = True
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
    if data_lines:
        payload = "\n".join(data_lines)
        if payload == "complete":
            saw_complete_sentinel = True
        else:
            event_count += 1

    return event_count, saw_complete_sentinel
