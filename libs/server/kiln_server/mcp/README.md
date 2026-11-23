# Kiln project tools MCP server [Beta]

> If you're looking for our MCP client to integrate third party MCP servers into the Kiln app, see https://docs.kiln.tech/docs/tools-and-mcp

> To connect your own agent (Claude Code, Codex, OpenCode) to the Kiln app, use the MCP server built into the app: see agent_install.md at the repo root. This server is not the way to do that.

The Kiln project tools MCP server (the `kiln_mcp` command) lets you call one Kiln project's tools, such as a Kiln Search Tool, from any MCP client.

**Beta** This is a beta intended for local usage. It isn't designed for production workloads.

### Installation

We suggest installing with uv:

```bash
uv tool install kiln_server
```

**Important** You must have run search indexing from the Kiln app before starting a Kiln search tool via this MCP server, on the same computer as you are running this MCP.

### Running kiln_mcp

Once installed, you can run `kiln_mcp` from your terminal. The last parameter must be the path to the project.kiln file you wish to use. Example:

```bash
kiln_mcp --transport streamable-http "/Users/username/Kiln Projects/Project Name/project.kiln"
```

### Running kiln_mcp in Cursor, VSCode, etc

Add Kiln to your `mcp.json` file, and your MCP client will launch the server over the stdio transport when it's invoked. Note: the JSON format the client expects can vary from app to app. Check your client's documentation for the exact format required.

```json
{
  "mcpServers": {
    "kilnMCP": {
      "command": "kiln_mcp",
      "args": ["/Users/username/Kiln Projects/Project Name/project.kiln"]
    }
  }
}
```

[![Install MCP Server](https://cursor.com/deeplink/mcp-install-dark.svg)](https://cursor.com/en-US/install-mcp?name=kiln_mcp&config=eyJjb21tYW5kIjoia2lsbl9tY3AgXCIvVXNlcnMvdXNlcm5hbWUvS2lsbiBQcm9qZWN0cy9Qcm9qZWN0IE5hbWUvcHJvamVjdC5raWxuXCIifQ%3D%3D)

### kiln_mcp Command Options

```
usage: kiln_mcp [-h] [--tool-ids TOOL_IDS] [--list-tools] [--transport {stdio,sse,streamable-http}] [--host HOST] [--port PORT] [--mount-path MOUNT_PATH]
                [--log-level LOG_LEVEL]
                project

Run the Kiln project tools MCP server: it serves one project's tools (such as search tools) to other apps. It does not connect your own agent, such as Claude
Code or Codex, to the Kiln app; for that, use the MCP server built into the Kiln app.

positional arguments:
  project               Path to the project.kiln file

options:
  -h, --help            show this help message and exit
  --tool-ids TOOL_IDS   Comma-separated list of tool IDs to expose. Defaults to all project tools. Use the --list-tools flag to list all available tool IDs for a
                        project.
  --list-tools          List all available tool IDs.
  --transport {stdio,sse,streamable-http}
                        Transport mechanism for the MCP server.
  --host HOST           Host for network transports.
  --port PORT           Port for network transports.
  --mount-path MOUNT_PATH
                        Optional mount path for SSE or streamable HTTP transports.
  --log-level LOG_LEVEL
                        Log level for the server when using network transports.
```
