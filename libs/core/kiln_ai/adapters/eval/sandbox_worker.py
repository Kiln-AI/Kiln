"""Multiprocessing worker for executing user-authored scorer functions.

Thin module: only imports stdlib and kiln_ai.sandbox (which is itself
stdlib-only). No Pydantic / Kiln-model / DB / UI imports.
"""

import inspect
import io
import multiprocessing
import multiprocessing.queues
import queue
import sys
import traceback
from typing import Any

from kiln_ai.sandbox.entrypoint import call_entrypoint
from kiln_ai.sandbox.spawn import start_process_with_light_main


def _execute_scorer(
    code: str,
    inputs: dict[str, Any],
    result_queue: multiprocessing.Queue,  # type: ignore[type-arg]
) -> None:
    """Target function for the child process.

    Runs user scorer code in an isolated namespace. Both ``def score``
    and ``async def score`` are supported -- if the call returns a
    coroutine it is transparently awaited via ``asyncio.run()``.

    Puts exactly one JSON-serializable dict on *result_queue*:
      - success:  {"ok": <result>, "stdout": ..., "stderr": ...}
      - error:    {"error": str, "traceback": str, "stdout": ..., "stderr": ...}
      - missing:  {"error": "...does not define score...", "stdout": ..., "stderr": ...}
    """
    # Redirect stdout/stderr to capture user prints and avoid None-stdout
    # crashes in frozen (PyInstaller --windowed) builds.
    captured_stdout = io.StringIO()
    captured_stderr = io.StringIO()
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    try:
        sys.stdout = captured_stdout
        sys.stderr = captured_stderr

        namespace: dict[str, Any] = {}
        exec(code, namespace)

        score_fn = namespace.get("score")
        if score_fn is None:
            result_queue.put(
                {
                    "error": "User code does not define a 'score()' function",
                    "stdout": captured_stdout.getvalue(),
                    "stderr": captured_stderr.getvalue(),
                }
            )
            return
        if not callable(score_fn):
            result_queue.put(
                {
                    "error": "'score' is defined but is not callable",
                    "stdout": captured_stdout.getvalue(),
                    "stderr": captured_stderr.getvalue(),
                }
            )
            return

        known_params = {
            "output": inputs["output"],
            "trace": inputs.get("trace"),
            "reference_data": inputs.get("reference_data"),
            "task_input": inputs["task_input"],
        }
        sig = inspect.signature(score_fn)
        declared = set(sig.parameters.keys())
        if not declared & {"output", "trace"}:
            result_queue.put(
                {
                    "error": "score() must accept at least 'output' or 'trace' as a parameter",
                    "stdout": captured_stdout.getvalue(),
                    "stderr": captured_stderr.getvalue(),
                }
            )
            return
        call_kwargs = {k: v for k, v in known_params.items() if k in declared}
        result = call_entrypoint(score_fn, call_kwargs)

        result_queue.put(
            {
                "ok": result,
                "stdout": captured_stdout.getvalue(),
                "stderr": captured_stderr.getvalue(),
            }
        )
    except Exception:
        result_queue.put(
            {
                "error": str(sys.exc_info()[1]),
                "traceback": traceback.format_exc(),
                "stdout": captured_stdout.getvalue(),
                "stderr": captured_stderr.getvalue(),
            }
        )
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr


def run_scorer(
    code: str,
    inputs: dict[str, Any],
    timeout: float,
) -> dict[str, Any]:
    """Spawn a child process to execute the user scorer, with wall-clock timeout.

    Uses an explicit ``spawn`` context so tests work regardless of the
    global start method.

    Returns a dict with either ``"ok"`` (success) or ``"error"`` key.
    Raises RuntimeError on timeout and on unexpected crash.
    """
    ctx = multiprocessing.get_context("spawn")
    q: multiprocessing.Queue = ctx.Queue()  # type: ignore[type-arg]
    p = ctx.Process(target=_execute_scorer, args=(code, inputs, q), daemon=True)
    start_process_with_light_main(p)
    p.join(timeout=timeout)

    if p.is_alive():
        p.kill()
        p.join(timeout=5)
        raise RuntimeError(f"Code eval scorer timed out after {timeout}s")

    try:
        result: dict[str, Any] = q.get_nowait()
    except queue.Empty:
        if p.exitcode not in (0, None):
            raise RuntimeError(f"Scorer crashed (exit code {p.exitcode})")
        raise RuntimeError("Scorer process exited without returning results")
    finally:
        q.close()
        q.join_thread()

    if p.exitcode not in (0, None) and "ok" not in result:
        raise RuntimeError(f"Scorer crashed (exit code {p.exitcode})")

    return result
