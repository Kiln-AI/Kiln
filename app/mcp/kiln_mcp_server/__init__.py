"""The Kiln MCP server, which connects a user's coding agent to the running
Kiln app."""

from kiln_mcp_server.server import MCP_PATH, KilnMcpServer, build_kiln_mcp_server

__all__ = ["MCP_PATH", "KilnMcpServer", "build_kiln_mcp_server"]
