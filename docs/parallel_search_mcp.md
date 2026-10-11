# Parallel Search MCP with the Kiln Python library

Use [Parallel Search MCP](https://docs.parallel.ai/integrations/mcp/search-mcp)
to search the web and fetch pages through Kiln's existing remote MCP tools.
The anonymous endpoint needs no Parallel account or API key. Search uses Fast
mode. The free service has rate limits and is intended for exploration and light
use.

This example calls the tools directly through Kiln's tool registry. It creates a
temporary project, saves the server configuration, reloads the project, and calls
`web_search` and `web_fetch`. It does not call a language model or change your
existing projects or model configuration.

## Run the example

From a checkout of this repository, install the workspace dependencies:

```bash
uv sync --locked
```

Run the following command from the repository root. The project is deleted when
the example exits. Each call prints the returned text, including source URLs and
excerpts.

```bash
uv run python - <<'PY'
import asyncio
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory

from kiln_ai.datamodel.external_tool_server import ExternalToolServer, ToolServerType
from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.tool_id import MCP_REMOTE_TOOL_ID_PREFIX
from kiln_ai.tools.mcp_session_manager import mcp_session_scope
from kiln_ai.tools.tool_registry import tool_from_id_and_project


async def main() -> None:
    with TemporaryDirectory(prefix="kiln-parallel-") as directory:
        project = Project(
            name="Parallel Search Example",
            path=Path(directory) / "project.kiln",
            created_by="parallel-search-example",
        )
        project.save_to_file()
        server = ExternalToolServer(
            name="Parallel Search",
            type=ToolServerType.remote_mcp,
            properties={
                "server_url": "https://search.parallel.ai/mcp",
                "headers": {"User-Agent": "Kiln/Parallel-Search-MCP-Example"},
                "secret_header_keys": [],
                "is_archived": False,
            },
            parent=project,
            created_by="parallel-search-example",
        )
        server.save_to_file()
        project = Project.load_from_file(project.path)
        session_id = uuid.uuid4().hex
        queries = ["Kiln remote MCP tools"]

        async with mcp_session_scope():
            search = tool_from_id_and_project(
                f"{MCP_REMOTE_TOOL_ID_PREFIX}{server.id}::web_search", project
            )
            result = await search.run(
                objective="Find how Kiln connects to remote MCP servers.",
                search_queries=queries,
                session_id=session_id,
            )
            if result.is_error:
                raise RuntimeError(result.error_message)
            print("SEARCH\n", result.output)

            fetch = tool_from_id_and_project(
                f"{MCP_REMOTE_TOOL_ID_PREFIX}{server.id}::web_fetch", project
            )
            result = await fetch.run(
                urls=["https://docs.kiln.tech/docs/tools-and-mcp"],
                objective="Find the settings for connecting a remote MCP server.",
                search_queries=queries,
                session_id=session_id,
            )
            if result.is_error:
                raise RuntimeError(result.error_message)
            print("FETCH\n", result.output)


asyncio.run(main())
PY
```

`mcp_session_scope()` keeps the MCP connection alive for both calls and closes it
on exit, including when a call fails. Both tools use one conversation identifier.
The saved server has no secret headers and sends no authentication credentials.

## Connect an existing project

In the Kiln app, open **Tools > Add Tools > Remote MCP > Connect**. Set the server
URL to `https://search.parallel.ai/mcp`. Add a non-secret `User-Agent` header with
the value `Kiln/Parallel-Search-MCP`. Leave authentication headers empty for the
anonymous service. Save the server and select `web_search` and `web_fetch` for
the task under **Advanced** on the **Run** screen.

For a Python project, save an `ExternalToolServer` with the same URL and headers
under the existing `Project`. Its tool IDs use
`mcp::remote::<server-id>::web_search` and
`mcp::remote::<server-id>::web_fetch`. Add only the tools your task needs to its
run configuration. Model execution uses your selected model and its usual
credentials.

If the service returns a rate limit, wait for its indicated retry time before
calling it again. Keep the same `session_id` for related calls in one conversation.
See the [Parallel MCP guide](https://docs.parallel.ai/integrations/mcp/search-mcp)
for current schemas and limits, and the
[Kiln tools guide](https://docs.kiln.tech/docs/tools-and-mcp) for task setup.
