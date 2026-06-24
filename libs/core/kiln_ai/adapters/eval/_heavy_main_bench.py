"""Heavy-__main__ benchmark harness for run_scorer.

This script deliberately imports a heavy module at the top level,
mimicking ``app/desktop/dev_server.py`` which has an unguarded
``from app.desktop.desktop_server import make_app`` plus
``dev_app = make_app()`` at module scope.

When invoked as ``python _heavy_main_bench.py``, *this file* is
``__main__``.  Under multiprocessing "spawn", the child process
re-imports the parent's ``__main__`` module during bootstrap
(``multiprocessing.spawn.get_preparation_data`` reads
``sys.modules['__main__'].__file__``).  So if ``run_scorer`` does NOT
prevent the re-import, the child re-executes the heavy import chain
(~1-3 s per call) -- the exact bug this benchmark catches.

Usage (from repo root):
    uv run python libs/core/kiln_ai/adapters/eval/_heavy_main_bench.py

Prints one JSON line per run_scorer call:
    {"call": 1, "elapsed": 2.345}

Exit code 0 on success.
"""

import json
import multiprocessing
import sys
import time

# ---- Heavy top-level import (mirrors the real server chain) ----
# litellm is the single heaviest transitive dependency (~0.8-1.5 s) and
# is part of the actual import chain that makes dev_server.py / the
# frozen desktop main so expensive to re-import.  Using it directly
# avoids needing tkinter/PIL/etc. that desktop_server.py also pulls in,
# while faithfully reproducing the mechanism: a slow top-level import
# that the spawn child would re-execute.
import litellm  # noqa: F401

from kiln_ai.adapters.eval.sandbox_worker import run_scorer

_TRIVIAL_CODE = (
    "def score(output, trace, reference_data, task_input):\n    return {'x': 1.0}\n"
)
_INPUTS = {
    "output": "hello",
    "trace": None,
    "reference_data": None,
    "task_input": "test",
}
_N = 2

if __name__ == "__main__":
    multiprocessing.freeze_support()

    for i in range(1, _N + 1):
        t0 = time.perf_counter()
        result = run_scorer(_TRIVIAL_CODE, _INPUTS, timeout=30)
        elapsed = time.perf_counter() - t0

        if "ok" not in result:
            print(
                json.dumps({"call": i, "error": result.get("error", "unknown")}),
                flush=True,
            )
            sys.exit(1)

        print(json.dumps({"call": i, "elapsed": round(elapsed, 4)}), flush=True)
