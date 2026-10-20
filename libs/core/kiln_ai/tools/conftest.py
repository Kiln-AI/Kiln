"""Shared fixtures for the MCP tool test suite."""

from __future__ import annotations

import socket
import subprocess
import sys
import time
from collections.abc import Iterator

import pytest

SERVER_MODULE = "kiln_ai.tools.mcp_echo_server_for_tests"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture(scope="session")
def mcp_echo_stdio_command() -> dict[str, object]:
    """The command properties that start the echo server over stdio."""
    return {
        "command": sys.executable,
        "args": ["-m", SERVER_MODULE, "stdio"],
        "env_vars": {},
        "is_archived": False,
    }


@pytest.fixture(scope="session")
def mcp_echo_http_url() -> Iterator[str]:
    """Start the echo server over streamable HTTP and yield its endpoint URL."""
    port = _free_port()
    process = subprocess.Popen(
        [sys.executable, "-m", SERVER_MODULE, "http"],
        env={"KILN_TEST_MCP_PORT": str(port), "PATH": ""},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}/mcp"
    try:
        _wait_until_listening(process, port)
        yield url
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


def _wait_until_listening(process: subprocess.Popen[bytes], port: int) -> None:
    """Block until the server accepts a connection, or fail the test."""
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"Echo server exited with code {process.returncode} before it listened"
            )
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError(f"Echo server did not listen on port {port} within 30s")
