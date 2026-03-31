"""Kiln API Call Tool - makes HTTP requests to the Kiln API server."""

import json
from typing import Any

import httpx
import jq

from kiln_ai.tools.base_tool import KilnTool, ToolCallResult


class KilnApiCallTool(KilnTool):
    """Tool for making HTTP requests to the Kiln API server."""

    def __init__(self, api_base_url: str = "http://localhost:8757"):
        self._api_base_url = api_base_url
        super().__init__(
            tool_id="kiln_tool::call_kiln_api",  # type: ignore[arg-type]
            name="call_kiln_api",
            description=self._build_description(),
            parameters_schema=self._build_parameters_schema(),
        )

    @staticmethod
    def _build_description() -> str:
        return """Call the Kiln API server. Makes an HTTP request to the specified path and returns the response.

The url_path is appended to the API base URL — provide only the path component (e.g. '/api/projects'), not a full URL.

For POST and PATCH requests, pass the request payload in the 'body' parameter. It can be a JSON string, a object, or a array. Objects and arrays are automatically serialized to JSON.

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
                    "description": "Request body for POST/PATCH requests. Can be a JSON string, a JSON object, or a JSON array. Objects and arrays are automatically serialized.",
                },
                "jq_filter": {
                    "type": "string",
                    "description": "A jq filter program (e.g. '.items[].name') to extract specific data from the response, reducing output size.",
                },
            },
            "required": ["method", "url_path"],
        }

    async def run(  # type: ignore[override]
        self,
        method: str,
        url_path: str,
        body: str | dict | list | None = None,
        jq_filter: str | None = None,
        context=None,
    ) -> ToolCallResult:
        body_str: str | None = None
        if isinstance(body, (dict, list)):
            body_str = json.dumps(body)
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

        if body_str is not None and method in {"GET", "DELETE"}:
            raise ValueError(f"body parameter not allowed with {method} method")

        # 2. Build full URL
        full_url = f"{self._api_base_url}{url_path}"

        # 3. Make HTTP request
        headers = {"Content-Type": "application/json"}
        # GET/DELETE: 30s, POST/PATCH: 5 minutes (may upload large data)
        timeout_seconds = 30.0 if method in {"GET", "DELETE"} else 300.0
        timeout = httpx.Timeout(timeout_seconds)

        async with httpx.AsyncClient(timeout=timeout) as client:
            request_funcs = {
                "GET": lambda: client.get(full_url, headers=headers),
                "POST": lambda: client.post(
                    full_url, headers=headers, content=body_str
                ),
                "PATCH": lambda: client.patch(
                    full_url, headers=headers, content=body_str
                ),
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

        # 4. Build response
        status_code = response.status_code
        response_text = response.text

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

        result = {"status_code": status_code, "body": response_body}
        return ToolCallResult(output=json.dumps(result))
