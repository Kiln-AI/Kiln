"""Multiprocessing worker for executing user-authored scorer functions.

Thin module: stdlib only. No Pydantic / Kiln-model / DB / UI imports.
"""

import asyncio
import inspect
import io
import multiprocessing
import multiprocessing.queues
import queue
import sys
import threading
import traceback
from typing import Any

_spawn_lock = threading.Lock()


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

        result = score_fn(
            output=inputs["output"],
            trace=inputs.get("trace"),
            reference_data=inputs.get("reference_data"),
            task_input=inputs["task_input"],
        )

        if inspect.iscoroutine(result):
            result = asyncio.run(result)

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
    with _spawn_lock:
        p = ctx.Process(target=_execute_scorer, args=(code, inputs, q), daemon=True)
        # Prevent the spawn child from re-importing the parent's heavy
        # ``__main__`` module (e.g. dev_server.py which transitively pulls
        # in litellm, google.cloud.aiplatform, etc.).
        #
        # ``multiprocessing.spawn.get_preparation_data`` reads
        # ``sys.modules['__main__']`` to decide what to re-execute in the
        # child.  By swapping in a lightweight stub named ``"__main__"``
        # (with no ``__file__`` or ``__spec__``) before ``p.start()``
        # (which pickles the prep data), neither ``init_main_from_name``
        # nor ``init_main_from_path`` is set, so the child skips the
        # heavy re-import entirely.  ``_execute_scorer`` only needs
        # stdlib, so this is safe.
        #
        # The stub is named ``"__main__"`` (not ``"__mp_main__"``, which
        # would collide with multiprocessing's internal main-module
        # name).  Third-party code that inspects
        # ``sys.modules["__main__"].__name__`` during the brief swap
        # window sees the expected ``"__main__"`` value.
        #
        # This stays within ``multiprocessing.spawn``'s existing
        # bootstrap, so ``freeze_support()`` and PyInstaller frozen
        # builds continue to work.
        #
        # Thread safety: the swap is process-global, but the window is
        # sub-millisecond (only spans ``p.start()``), is serialized by
        # ``_spawn_lock``, and ``__main__`` is not read by request-
        # handling code, so cross-thread visibility is benign.
        import types

        _real_main = sys.modules.get("__main__")
        if _real_main is not None:
            _light_main = types.ModuleType("__main__")
            sys.modules["__main__"] = _light_main
            try:
                p.start()
            finally:
                sys.modules["__main__"] = _real_main
        else:
            p.start()
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
