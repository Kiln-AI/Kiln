"""Shared fixtures for the MCP tool test suite."""

from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from typing import Any

import pytest
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamablehttp_client

SERVER_MODULE = "kiln_ai.tools.mcp_echo_server_for_tests"
START_ATTEMPTS = 3
READY_TIMEOUT_SECONDS = 30


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
    process, url, log = _start_server()
    try:
        yield url
    finally:
        _stop_server(process)
        log.close()


def _start_server() -> tuple[subprocess.Popen[bytes], str, Any]:
    """Start the server, retrying because another worker can take the port first."""
    failures: list[str] = []
    for _ in range(START_ATTEMPTS):
        port = _free_port()
        url = f"http://127.0.0.1:{port}/mcp"
        log = tempfile.TemporaryFile()
        process = subprocess.Popen(
            [sys.executable, "-m", SERVER_MODULE, "http"],
            env={**os.environ, "KILN_TEST_MCP_PORT": str(port)},
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        error = _wait_until_ready(process, url)
        if error is None:
            return process, url, log
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


def _wait_until_ready(process: subprocess.Popen[bytes], url: str) -> str | None:
    """Wait for an MCP handshake to succeed. Return the reason on failure.

    The handshake is the readiness check because it answers both questions at
    once: the server listens, and the thing that answers is our MCP server. A
    bare connection to the port answers neither, since a process that already
    held the port accepts it just as well.
    """
    deadline = asyncio.get_event_loop_policy().new_event_loop()
    try:
        return deadline.run_until_complete(_handshake_until_ready(process, url))
    finally:
        deadline.close()


async def _handshake_until_ready(
    process: subprocess.Popen[bytes], url: str
) -> str | None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + READY_TIMEOUT_SECONDS
    last = "no attempt completed"
    while loop.time() < deadline:
        if process.poll() is not None:
            return f"the server exited with code {process.returncode}"
        try:
            async with streamablehttp_client(url) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
            return None
        except Exception as error:
            last = f"{type(error).__name__}: {error}"
            await asyncio.sleep(0.2)
    return f"no MCP handshake within {READY_TIMEOUT_SECONDS}s, last error {last}"


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
    """The end of the server output, so a start failure explains itself.

    This reads with pread because the child inherited this file as its stdout.
    A duplicated descriptor shares its offset, so a seek here would move the
    position the child writes at and could overwrite what it already logged.
    """
    size = os.fstat(log.fileno()).st_size
    start = max(0, size - limit)
    return os.pread(log.fileno(), limit, start).decode(errors="replace")
