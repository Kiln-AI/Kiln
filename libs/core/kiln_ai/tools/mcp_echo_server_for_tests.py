"""A minimal MCP server the integration tests run against.

The MCP integration tests used to point at a public server that no longer
resolves, and at a local server that needed an API key, so all of them were
skipped. This server runs from the `mcp` dependency we already have, over
either transport, with no network access and no credentials.

Run it as `python -m kiln_ai.tools.mcp_echo_server_for_tests [stdio|http]`.
The HTTP transport requires KILN_TEST_MCP_PORT.
"""

import os
import sys
import threading
import time

from mcp.server.fastmcp import FastMCP

HOST = "127.0.0.1"
TRANSPORTS = ("stdio", "http")

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


def _exit_with_parent() -> None:
    """Exit when the parent goes away, so a killed test run leaves nothing behind.

    The HTTP transport runs until something stops it. A test runner that dies
    without running its teardown, from a kill or a crash, would otherwise leave
    this process holding its port.
    """
    original = os.getppid()

    def watch() -> None:
        while os.getppid() == original:
            time.sleep(1)
        os._exit(0)

    threading.Thread(target=watch, daemon=True).start()


def main() -> None:
    transport = sys.argv[1] if len(sys.argv) > 1 else "stdio"
    if transport not in TRANSPORTS:
        raise SystemExit(f"Unknown transport {transport!r}. Use one of {TRANSPORTS}.")

    if transport == "http":
        port = os.environ.get("KILN_TEST_MCP_PORT")
        if not port:
            raise SystemExit("The http transport requires KILN_TEST_MCP_PORT.")
        # Set the host rather than inherit it, because the tests connect to a
        # fixed address and the default is the library's to change.
        mcp.settings.host = HOST
        mcp.settings.port = int(port)
        _exit_with_parent()
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
