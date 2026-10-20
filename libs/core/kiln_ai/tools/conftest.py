"""Shared fixtures for the MCP tool test suite."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator
from typing import Any

import pytest

SERVER_MODULE = "kiln_ai.tools.mcp_echo_server_for_tests"
START_ATTEMPTS = 3
LISTEN_TIMEOUT_SECONDS = 30


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
    process, port, log = _start_server()
    try:
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        _stop_server(process)
        log.close()


def _start_server() -> tuple[subprocess.Popen[bytes], int, Any]:
    """Start the server, retrying because another worker can take the port first."""
    failures: list[str] = []
    for _ in range(START_ATTEMPTS):
        port = _free_port()
        log = tempfile.TemporaryFile()
        process = subprocess.Popen(
            [sys.executable, "-m", SERVER_MODULE, "http"],
            env={**os.environ, "KILN_TEST_MCP_PORT": str(port)},
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        error = _wait_until_listening(process, port, log)
        if error is None:
            return process, port, log
        failures.append(f"port {port}: {error}\n{_tail(log)}")
        _stop_server(process)
        log.close()
    raise RuntimeError(
        "The echo server did not start. Attempts:\n" + "\n".join(failures)
    )


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_until_listening(
    process: subprocess.Popen[bytes], port: int, process_log: Any
) -> str | None:
    """Wait for the server to report that it listens. Return the reason on failure.

    Readiness comes from the server's own output, not from a connection to the
    port. A connection proves only that something listens there, and another
    process that already held the port answers it just as well.
    """
    expected = f"Uvicorn running on http://127.0.0.1:{port}"
    deadline = time.monotonic() + LISTEN_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if expected in _tail(process_log):
            return None
        if process.poll() is not None:
            return f"the server exited with code {process.returncode}"
        time.sleep(0.1)
    return f"the server did not report a listener within {LISTEN_TIMEOUT_SECONDS}s"


def _stop_server(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


def _tail(log: Any, limit: int = 2000) -> str:
    """The end of the server output, so a start failure explains itself."""
    log.flush()
    log.seek(0)
    return log.read()[-limit:].decode(errors="replace")
