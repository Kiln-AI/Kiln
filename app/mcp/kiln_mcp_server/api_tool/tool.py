"""Registers `call_kiln_api` on the MCP server."""

from dataclasses import dataclass
from typing import Annotated, Any

import httpx
from mcp.server.fastmcp import Context, FastMCP
from mcp.types import CallToolResult
from pydantic import Field

from kiln_mcp_server.api_tool.pipeline import QueryValue, run_api_call
from kiln_mcp_server.api_tool.policy import ConnectionPolicy
from kiln_mcp_server.api_tool.route_index import RouteIndex
from kiln_mcp_server.api_tool.tmp_files import TmpFileStore
from kiln_mcp_server.texts import CALL_KILN_API_DESCRIPTION

CALL_KILN_API_TOOL_NAME = "call_kiln_api"
DEFAULT_BODY_LIMIT = 30000

METHOD_DESCRIPTION = "HTTP method: GET, POST, PATCH or DELETE."
URL_PATH_DESCRIPTION = "API path, for example `/api/projects`. No query string: pass query arguments in `query_params`. Correct paths are in the endpoint docs."
BODY_DESCRIPTION = "JSON request body for POST and PATCH: an object, an array, or a string that holds JSON. Not allowed with GET or DELETE. The schema is in the endpoint doc."
QUERY_PARAMS_DESCRIPTION = "Query parameters as an object. Values are strings, numbers or booleans. A list repeats the key (`?ids=a&ids=b`)."
JQ_FILTER_DESCRIPTION = "Optional jq expression applied to a successful (2xx) JSON response before it is returned or saved."
BODY_LIMIT_DESCRIPTION = "Longest body, in characters, that a GET may return. Pass a higher number only when you need the whole body in your context."
SAVE_TO_TMPFILE_DESCRIPTION = "When true, the body of a successful response is written to a temporary file on the machine that runs Kiln. The result then holds `status_code`, `body_path` and `size_bytes`, and no `body`. Use the file with shell tools such as jq or grep. An error response is still returned inline."


@dataclass(frozen=True)
class ApiToolDeps:
    """What `call_kiln_api` needs from the server that registers it."""

    api_base_url: str
    route_index: RouteIndex
    policy: ConnectionPolicy
    tmp_files: TmpFileStore
    transport: httpx.AsyncBaseTransport | None = None
    progress_interval: float = 2.0


def register_call_kiln_api(mcp: FastMCP, deps: ApiToolDeps) -> None:
    @mcp.tool(
        name=CALL_KILN_API_TOOL_NAME,
        description=CALL_KILN_API_DESCRIPTION,
        structured_output=False,
    )
    async def call_kiln_api(
        method: Annotated[
            str,
            Field(
                description=METHOD_DESCRIPTION,
                json_schema_extra={"enum": ["GET", "POST", "PATCH", "DELETE"]},
            ),
        ],
        url_path: Annotated[str, Field(description=URL_PATH_DESCRIPTION)],
        ctx: Context,
        body: Annotated[
            dict[str, Any] | list[Any] | str | None,
            Field(description=BODY_DESCRIPTION),
        ] = None,
        query_params: Annotated[
            dict[str, QueryValue | None | list[QueryValue]] | None,
            Field(description=QUERY_PARAMS_DESCRIPTION),
        ] = None,
        jq_filter: Annotated[
            str | None, Field(description=JQ_FILTER_DESCRIPTION)
        ] = None,
        body_limit: Annotated[
            int, Field(description=BODY_LIMIT_DESCRIPTION)
        ] = DEFAULT_BODY_LIMIT,
        save_to_tmpfile: Annotated[
            bool, Field(description=SAVE_TO_TMPFILE_DESCRIPTION)
        ] = False,
    ) -> CallToolResult:
        return await run_api_call(
            deps,
            ctx.request_context.request,
            ctx.report_progress,
            method=method,
            url_path=url_path,
            body=body,
            query_params=query_params,
            jq_filter=jq_filter,
            body_limit=body_limit,
            save_to_tmpfile=save_to_tmpfile,
        )
