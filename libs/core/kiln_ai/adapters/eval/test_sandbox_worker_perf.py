"""Benchmarks for sandbox_worker / code-eval subprocess performance.

These benchmarks measure the end-to-end cost of spawning a child process
via ``run_scorer`` at various levels of code complexity.  With lazy
``__init__.py`` imports, the child process no longer loads the full
kiln_ai.adapters package chain, so ``run_scorer`` completes in tens of
milliseconds rather than seconds.

Marked ``@pytest.mark.slow`` so they are skipped in normal CI runs (requires
``--runslow`` to execute). Also marked ``@pytest.mark.benchmark`` for
categorisation; that marker does not skip tests — ``--benchmark-quiet`` only
suppresses benchmark output formatting.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from kiln_ai.adapters.eval.sandbox_worker import run_scorer

_EVAL_HELPERS_PATH = Path(__file__).resolve().parent / "eval_helpers.py"

_INPUTS: dict = {
    "output": "hello world",
    "trace": None,
    "reference_data": None,
    "task_input": "test input",
}

TRIVIAL_CODE = (
    "def score(output, trace, reference_data, task_input):\n    return {'x': 1.0}\n"
)

STDLIB_IMPORT_CODE = (
    "import math\nimport json\nimport re\n"
    "def score(output, trace, reference_data, task_input):\n"
    "    return {'x': math.sqrt(4)}\n"
)

KILN_HELPERS_CODE = (
    "from kiln_ai.adapters.eval.eval_helpers import KilnEvalHelpers\n"
    "def score(output, trace, reference_data, task_input):\n"
    "    return {'x': KilnEvalHelpers.pass_fail(True)}\n"
)


# ---------------------------------------------------------------------------
# run_scorer benchmarks (multiprocessing.spawn with lazy __init__)
# ---------------------------------------------------------------------------


@pytest.mark.benchmark
@pytest.mark.slow
def test_benchmark_run_scorer_trivial(benchmark):
    """Spawn + trivial scorer (return constant, no imports)."""

    def run():
        result = run_scorer(TRIVIAL_CODE, _INPUTS, timeout=30)
        assert "ok" in result

    benchmark.pedantic(run, rounds=10, iterations=1)
    mean = benchmark.stats.stats.mean
    assert mean < 0.5, f"Trivial scorer averaged {mean:.2f}s — expected under 0.5s"


@pytest.mark.benchmark
@pytest.mark.slow
def test_benchmark_run_scorer_stdlib_imports(benchmark):
    """Spawn + scorer that imports stdlib modules (math, json, re)."""

    def run():
        result = run_scorer(STDLIB_IMPORT_CODE, _INPUTS, timeout=30)
        assert "ok" in result

    benchmark.pedantic(run, rounds=10, iterations=1)
    mean = benchmark.stats.stats.mean
    assert mean < 0.5, f"Stdlib scorer averaged {mean:.2f}s — expected under 0.5s"


@pytest.mark.benchmark
@pytest.mark.slow
def test_benchmark_run_scorer_kiln_helpers(benchmark):
    """Spawn + scorer that uses KilnEvalHelpers (explicit import in scorer code)."""

    def run():
        result = run_scorer(KILN_HELPERS_CODE, _INPUTS, timeout=30)
        assert "ok" in result

    benchmark.pedantic(run, rounds=10, iterations=1)
    mean = benchmark.stats.stats.mean
    assert mean < 0.5, f"Kiln-helpers scorer averaged {mean:.2f}s — expected under 0.5s"


# ---------------------------------------------------------------------------
# Baseline: raw subprocess (no kiln_ai package imports in the child)
# ---------------------------------------------------------------------------


@pytest.mark.benchmark
@pytest.mark.slow
def test_benchmark_raw_subprocess_baseline(benchmark):
    """Raw subprocess.run(python -c ...) executing the same trivial scorer.

    This measures the *achievable* floor: Python interpreter startup + exec
    of user code, with zero package imports in the child process.
    """
    wrapper = (
        "import sys, json; "
        "inputs = json.loads(sys.argv[1]); "
        "code = sys.argv[2]; "
        "ns = {}; exec(code, ns); "
        "r = ns['score'](output=inputs['output'], trace=inputs.get('trace'), "
        "reference_data=inputs.get('reference_data'), task_input=inputs['task_input']); "
        "print(json.dumps(r))"
    )
    inputs_json = json.dumps(_INPUTS)

    def run():
        proc = subprocess.run(
            [sys.executable, "-c", wrapper, inputs_json, TRIVIAL_CODE],
            capture_output=True,
            timeout=30,
        )
        assert proc.returncode == 0

    benchmark.pedantic(run, rounds=10, iterations=1)
    mean = benchmark.stats.stats.mean
    assert mean < 0.5, f"Raw subprocess averaged {mean:.2f}s — expected under 0.5s"


# ---------------------------------------------------------------------------
# Import-chain isolation: subprocess measuring only the import cost
# ---------------------------------------------------------------------------


@pytest.mark.benchmark
@pytest.mark.slow
def test_benchmark_import_chain_adapters(benchmark):
    """Subprocess that only does ``import kiln_ai.adapters``.

    With lazy __init__.py this should be fast (no transitive imports).
    """

    def run():
        proc = subprocess.run(
            [sys.executable, "-c", "import kiln_ai.adapters"],
            capture_output=True,
            timeout=30,
        )
        assert proc.returncode == 0

    benchmark.pedantic(run, rounds=10, iterations=1)
    mean = benchmark.stats.stats.mean
    assert mean < 0.5, f"Import chain averaged {mean:.2f}s — expected under 0.5s"


@pytest.mark.benchmark
@pytest.mark.slow
def test_benchmark_import_eval_helpers_direct(benchmark):
    """Subprocess that imports eval_helpers by file path (no package chain).

    This shows the cost of the eval_helpers module itself, without the
    transitive kiln_ai.adapters package init.
    """
    import_stmt = (
        "import importlib.util; "
        "spec = importlib.util.spec_from_file_location('eval_helpers', "
        f"'{_EVAL_HELPERS_PATH}'); "
        "mod = importlib.util.module_from_spec(spec); "
        "spec.loader.exec_module(mod)"
    )

    def run():
        proc = subprocess.run(
            [sys.executable, "-c", import_stmt],
            capture_output=True,
            timeout=30,
        )
        assert proc.returncode == 0

    benchmark.pedantic(run, rounds=10, iterations=1)
    mean = benchmark.stats.stats.mean
    assert mean < 0.5, (
        f"Direct eval_helpers import averaged {mean:.2f}s — expected under 0.5s"
    )


# ---------------------------------------------------------------------------
# Heavy-__main__ benchmark: faithful reproduction of the real server cost
# ---------------------------------------------------------------------------

_HEAVY_MAIN_SCRIPT = Path(__file__).resolve().parent / "_heavy_main_bench.py"


@pytest.mark.benchmark
@pytest.mark.slow
def test_benchmark_run_scorer_heavy_main():
    """run_scorer called from a process whose __main__ imports litellm.

    This faithfully reproduces the real ``POST .../test_v2_eval`` cost:
    the helper script imports ``litellm`` at module level (the heaviest
    dep in the server chain, ~0.8-1.5 s), so when multiprocessing
    "spawn" tries to re-import ``__main__`` in the child, the heavy
    import would be re-executed -- unless the fix in ``run_scorer``
    prevents the heavy re-import.

    Pre-fix: each call takes ~1-3s (child re-imports the heavy main).
    Post-fix: each call takes ~50ms (child skips the heavy main).
    Assertion bound: 250ms (generous CI buffer; local expectation ~50ms).

    Source-only: uses ``sys.executable`` which is the Python interpreter
    from source, not the app bundle.  This benchmark is never run in a
    frozen (PyInstaller) build.
    """
    proc = subprocess.run(
        [sys.executable, str(_HEAVY_MAIN_SCRIPT)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, (
        f"Heavy-main benchmark failed:\nstdout: {proc.stdout}\nstderr: {proc.stderr}"
    )

    lines = [ln for ln in proc.stdout.strip().splitlines() if ln.strip()]
    assert len(lines) == 2, f"Expected 2 result lines, got {len(lines)}: {lines}"

    for line in lines:
        data = json.loads(line)
        assert "elapsed" in data, f"Unexpected output: {data}"
        elapsed = data["elapsed"]
        assert elapsed < 0.25, (
            f"run_scorer call {data['call']} took {elapsed:.3f}s — "
            f"expected <0.25s (local ~0.05s, CI buffer 0.25s). "
            f"The spawn child is likely re-importing the heavy __main__."
        )
