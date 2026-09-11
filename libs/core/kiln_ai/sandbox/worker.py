"""Child-process entry point for code-tool execution.

Stdlib only — no Pydantic / Kiln-model / DB / UI imports.

The parent spawns this via ``multiprocessing`` (spawn context).
Communication uses two queues (requests child->parent, responses parent->child).
"""

from __future__ import annotations

import io
import json
import sys
import traceback
from multiprocessing import Queue
from typing import Any

from kiln_ai.sandbox.entrypoint import call_entrypoint
from kiln_ai.sandbox.tools_api import install_tools_modules

_TRUNCATION_LIMIT = 64 * 1024  # 64 KB
_TRUNCATION_MARKER = "\n...[truncated]"


def child_main(
    code: str,
    kwargs: dict[str, Any],
    requests: Queue,  # type: ignore[type-arg]
    responses: Queue,  # type: ignore[type-arg]
) -> None:
    """Entry point for the code-tool child process.

    Puts exactly one ``result`` message on *requests* and then returns.
    """
    captured_stdout = io.StringIO()
    captured_stderr = io.StringIO()
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    try:
        sys.stdout = captured_stdout  # type: ignore[assignment]
        sys.stderr = captured_stderr  # type: ignore[assignment]

        install_tools_modules(requests, responses)

        namespace: dict[str, Any] = {}
        exec(compile(code, "<code_tool>", "exec"), namespace)

        run_fn = namespace.get("run")
        if run_fn is None:
            _put_error(
                requests,
                "Code does not define a 'run()' function",
                None,
                captured_stdout,
                captured_stderr,
            )
            return
        if not callable(run_fn):
            _put_error(
                requests,
                "'run' is defined but is not callable",
                None,
                captured_stdout,
                captured_stderr,
            )
            return

        result = call_entrypoint(run_fn, kwargs)
        serialized = _serialize_result(result)

        requests.put(
            {
                "type": "result",
                "ok": serialized,
                "stdout": _truncate(captured_stdout.getvalue()),
                "stderr": _truncate(captured_stderr.getvalue()),
            }
        )
    except Exception:
        tb = _trim_traceback()
        exc_info = sys.exc_info()
        _put_error(
            requests,
            str(exc_info[1]),
            tb,
            captured_stdout,
            captured_stderr,
        )
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _serialize_result(value: Any) -> str:
    """Serialize the return value of ``run()`` per the spec.

    - ``str`` passes through as-is.
    - ``dict/list/int/float/bool/None`` -> ``json.dumps``.
    - Anything else -> raise with a clear message.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list, int, float, bool)) or value is None:
        try:
            return json.dumps(value, ensure_ascii=False)
        except (TypeError, ValueError) as exc:
            raise TypeError(
                f"run() returned a value containing non-JSON-serializable data: {exc}"
            ) from exc
    raise TypeError(
        f"run() must return str or JSON-serializable data, got {type(value).__name__}"
    )


def _trim_traceback() -> str:
    """Format the current exception traceback, keeping only ``<code_tool>`` frames."""
    _, exc_value, exc_tb = sys.exc_info()
    if exc_value is None or exc_tb is None:
        return ""

    entries = traceback.extract_tb(exc_tb)
    first_user_idx = None
    for i, frame in enumerate(entries):
        if frame.filename == "<code_tool>":
            first_user_idx = i
            break

    if first_user_idx is not None:
        entries = entries[first_user_idx:]

    lines = ["Traceback (most recent call last):\n"]
    lines.extend(traceback.format_list(entries))
    lines.extend(traceback.format_exception_only(type(exc_value), exc_value))
    return "".join(lines)


def _truncate(text: str) -> str:
    if len(text) <= _TRUNCATION_LIMIT:
        return text
    return text[:_TRUNCATION_LIMIT] + _TRUNCATION_MARKER


def _put_error(
    queue: Queue,  # type: ignore[type-arg]
    error: str,
    tb: str | None,
    stdout: io.StringIO,
    stderr: io.StringIO,
) -> None:
    queue.put(
        {
            "type": "result",
            "error": error,
            "traceback": tb,
            "stdout": _truncate(stdout.getvalue()),
            "stderr": _truncate(stderr.getvalue()),
        }
    )
