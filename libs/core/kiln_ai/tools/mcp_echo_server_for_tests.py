"""A minimal MCP server the integration tests run against.

The MCP integration tests used to point at a public server that no longer
resolves, and at a local server that needed an API key, so all of them were
skipped. This server runs from the `mcp` dependency we already have, over
either transport, with no network access and no credentials.

Run it as `python -m kiln_ai.tools.mcp_echo_server_for_tests [stdio|http]`.
The HTTP transport reads its port from KILN_TEST_MCP_PORT.
"""

import os
import sys

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("kiln-test-echo")


@mcp.tool(structured_output=False)
def echo(message: str) -> str:
    """Return the message, prefixed, so a caller can assert a round trip."""
    return f"Tool echo: {message}"


@mcp.tool(structured_output=False)
def echo_env(name: str) -> str:
    """Return an environment variable, so a caller can assert it arrived.

    A local server reaches its credentials through the environment, so a test
    needs to see that the variables the caller set reach this process.
    """
    return os.environ.get(name, "<unset>")


def main() -> None:
    transport = sys.argv[1] if len(sys.argv) > 1 else "stdio"
    if transport == "http":
        mcp.settings.port = int(os.environ.get("KILN_TEST_MCP_PORT", "3999"))
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
