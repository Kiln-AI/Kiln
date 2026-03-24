"""Kiln API Call Tool - makes HTTP requests to the Kiln API server."""

import json
from typing import Any

import httpx
import jq

from kiln_ai.datamodel.tool_id import KilnBuiltInToolId
from kiln_ai.tools.base_tool import KilnTool, ToolCallResult
from kiln_ai.utils.config import Config


def kiln_local_api_base_url() -> str:
    configured = Config.shared().kiln_local_api_base_url
    if configured:
        return configured
    return "http://127.0.0.1:8757"


class KilnApiCallTool(KilnTool):
    def __init__(self, api_base_url: str | None = None):
        self._api_base_url_override = api_base_url
        super().__init__(
            tool_id=KilnBuiltInToolId.CALL_KILN_API,
            name="call_kiln_api",
            description=self._build_description(),
            parameters_schema=self._build_parameters_schema(),
        )

    def _effective_base_url(self) -> str:
        if self._api_base_url_override is not None:
            return self._api_base_url_override
        return kiln_local_api_base_url()

    @staticmethod
    def _build_description() -> str:
        return """Call the Kiln API server. Makes an HTTP request to the specified path and returns the response.

The url_path is appended to the API base URL — provide only the path component (e.g. '/api/projects'), not a full URL.

For POST and PATCH requests, pass the request payload as a JSON string in the 'body' parameter.

Use 'jq_filter' to extract specific fields from the response using jq syntax (e.g. '.name', '.items[] | .id'). This reduces the response size. The filter is only applied to successful (2xx) responses; error responses are returned in full. If the filter produces no output, the body will be an empty string.

The response is a JSON object with 'status_code' (integer) and 'body' (string) fields."""

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
                    "description": "API path (e.g. '/api/projects'). Appended to the base URL.",
                },
                "body": {
                    "type": "string",
                    "description": "Request body for POST/PATCH requests, typically a JSON string.",
                },
                "jq_filter": {
                    "type": "string",
                    "description": "A jq filter program (e.g. '.items[].name') to extract specific data from the response, reducing output size.",
                },
            },
            "required": ["method", "url_path"],
        }

    async def run(self, context=None, **kwargs) -> ToolCallResult:
        method = str(kwargs.get("method", "")).upper()
        url_path = kwargs.get("url_path")
        body = kwargs.get("body")
        jq_filter = kwargs.get("jq_filter")

        if url_path is None:
            raise ValueError("url_path is required")

        allowed_methods = {"GET", "POST", "PATCH", "DELETE"}
        if method not in allowed_methods:
            raise ValueError(
                f"Invalid method '{method}'. Must be one of: {', '.join(sorted(allowed_methods))}"
            )

        if not isinstance(url_path, str) or not url_path.startswith("/"):
            raise ValueError(f"url_path must start with '/', got: {url_path}")

        if body is not None and method in {"GET", "DELETE"}:
            raise ValueError(f"body parameter not allowed with {method} method")

        base = self._effective_base_url()
        full_url = f"{base}{url_path}"

        headers = {"Content-Type": "application/json"}
        timeout_seconds = 30.0 if method in {"GET", "DELETE"} else 300.0
        timeout = httpx.Timeout(timeout_seconds)

        async with httpx.AsyncClient(timeout=timeout) as client:
            request_funcs = {
                "GET": lambda: client.get(full_url, headers=headers),
                "POST": lambda: client.post(full_url, headers=headers, content=body),
                "PATCH": lambda: client.patch(full_url, headers=headers, content=body),
                "DELETE": lambda: client.delete(full_url, headers=headers),
            }
            try:
                response = await request_funcs[method]()
            except httpx.TimeoutException:
                raise TimeoutError(
                    f"Request to {url_path} timed out after {timeout_seconds}s"
                )
            except httpx.ConnectError:
                raise ConnectionError(f"Could not connect to server for {url_path}")

        status_code = response.status_code
        response_text = response.text

        if jq_filter and isinstance(jq_filter, str) and 200 <= status_code < 300:
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
            response_body = response_text

        result = {"status_code": status_code, "body": response_body}
        return ToolCallResult(output=json.dumps(result))
