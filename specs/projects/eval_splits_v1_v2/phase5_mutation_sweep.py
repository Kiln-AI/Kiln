"""Mutation-test every behavior phase 5 of the eval-splits project claims to cover.

Same harness as phase2/phase3/phase4_mutation_sweep.py: each mutation applies one or
more textual edits to the tree, runs a test file, and expects it to fail. Run from
anywhere:

    uv run python specs/projects/eval_splits_v1_v2/phase5_mutation_sweep.py

Pass substrings to run a subset. Expected result: every mutation killed.
"""

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]

WORKER = "app/desktop/studio_server/jobs/workers/eval.py"
JOBS_API = "app/desktop/studio_server/jobs/api.py"

TWORKER = "app/desktop/studio_server/jobs/workers/test_eval.py"
TJOBS_API = "app/desktop/studio_server/jobs/test_api.py"

MUTATIONS = [
    # -- the requested split is the one that runs (functional spec 4.1, 4.2) ---
    (
        "_resolve_split: ignores the requested split and always runs test",
        [
            (
                WORKER,
                '        name: EvalSplitName = params.split or "test"',
                '        name: EvalSplitName = "test"',
            )
        ],
        TWORKER,
    ),
    (
        "_resolve_split: an omitted split defaults to something other than test",
        [
            (
                WORKER,
                '        name: EvalSplitName = params.split or "test"',
                '        name: EvalSplitName = params.split or "train"',
            )
        ],
        TWORKER,
    ),
    (
        # An absent split reported as an empty one is the shape functional spec 4.3
        # is about: the job succeeds having done nothing, and a resume agrees.
        "_resolve_split: an absent split degrades to an empty one instead of raising",
        [
            (
                WORKER,
                "        if split is None:\n            raise ValueError(f\"Eval '{eval.id}' has no '{name}' split.\")",
                '        if split is None:\n            return ResolvedSplit(name=name, source="task_run", items=[], eval_id=eval.id)',
            )
        ],
        TWORKER,
    ),
    # -- one resolution, two consumers (architecture 5.1) ---------------------
    (
        # The headline claim of this phase. Progress measured over a different set
        # than the runner works is exactly what let an EvalInput-backed job report a
        # zero total, and a train job short-circuit against the test split's count.
        "compute_state: measures the test split while the runner runs the requested one",
        [
            (
                WORKER,
                "        split = self._resolve_split(eval, task, params)",
                '        split = self._resolve_split(eval, task, params.model_copy(update={"split": "test"}))',
            )
        ],
        TWORKER,
    ),
    (
        "_build_eval_runner: resolves test independently of the requested split",
        [
            (
                WORKER,
                "            split=self._resolve_split(eval, task, params),",
                '            split=self._resolve_split(eval, task, params.model_copy(update={"split": "test"})),',
            )
        ],
        TWORKER,
    ),
    (
        "compute_state: total counts the task's runs rather than the split",
        [
            (
                WORKER,
                "        total = len(split)",
                "        total = len(task.runs(readonly=True))",
            )
        ],
        TWORKER,
    ),
    # -- membership is source-aware (architecture 3.1, functional spec 5.3) ---
    (
        "compute_state: scored items keyed on the bare id",
        [
            (
                WORKER,
                "            eval_run_item_key(run)\n            for run in eval_config.runs(readonly=True)",
                "            eval_run_item_key(run)[1]\n            for run in eval_config.runs(readonly=True)",
            )
        ],
        TWORKER,
    ),
    (
        "compute_state: split items keyed on the bare id",
        [
            (
                WORKER,
                "        split_items = split.item_keys()",
                "        split_items = {key[1] for key in split.item_keys()}",
            )
        ],
        TWORKER,
    ),
    (
        # Both halves together: membership still works, but on bare ids, so a
        # TaskRun's result can be credited to an EvalInput carrying the same id.
        # Only the id-collision test can kill this one.
        "compute_state: membership keyed on bare ids in both sets",
        [
            (
                WORKER,
                "            eval_run_item_key(run)\n            for run in eval_config.runs(readonly=True)",
                "            eval_run_item_key(run)[1]\n            for run in eval_config.runs(readonly=True)",
            ),
            (
                WORKER,
                "        split_items = split.item_keys()",
                "        split_items = {key[1] for key in split.item_keys()}",
            ),
        ],
        TWORKER,
    ),
    # -- a bad split 422s at request time (architecture 5.2, spec 9) ----------
    (
        "jobs/api: the pre-check is dropped, so a bad split becomes a doomed job",
        [
            (
                JOBS_API,
                "        if params.split is not None:\n            await asyncio.to_thread(\n                _require_resolvable_split,",
                "        if False:\n            await asyncio.to_thread(\n                _require_resolvable_split,",
            )
        ],
        TJOBS_API,
    ),
    (
        "jobs/api: the pre-check fires only when no split was named",
        [
            (
                JOBS_API,
                "        if params.split is not None:",
                "        if params.split is None:",
            )
        ],
        TJOBS_API,
    ),
    (
        "jobs/api: the pre-check resolves test rather than the split requested",
        [
            (
                JOBS_API,
                "                params.eval_id,\n                params.split,",
                '                params.eval_id,\n                "test",',
            )
        ],
        TJOBS_API,
    ),
    (
        "jobs/api: a 422 for the missing split still creates the job",
        [
            (
                JOBS_API,
                "    eval = eval_from_id(project_id, task_id, eval_id)\n    task = task_from_id(project_id, task_id)\n    resolved_split_or_422(task, eval, split)",
                "    eval = eval_from_id(project_id, task_id, eval_id)\n    task = task_from_id(project_id, task_id)",
            )
        ],
        TJOBS_API,
    ),
]


def run(label, edits, tests):
    originals = {}
    try:
        for path, old, new in edits:
            f = REPO / path
            if path not in originals:
                originals[path] = f.read_text()
            current = f.read_text()
            if current.count(old) != 1:
                return label, "PATTERN-MISS", f"({path}: count={current.count(old)})"
            f.write_text(current.replace(old, new))
        r = subprocess.run(
            [
                "uv",
                "run",
                "python",
                "-m",
                "pytest",
                "-q",
                "-x",
                "--no-header",
                "-p",
                "no:randomly",
                *tests.split(),
            ],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        return label, ("killed" if r.returncode != 0 else "SURVIVED"), ""
    finally:
        for path, text in originals.items():
            (REPO / path).write_text(text)


if __name__ == "__main__":
    only = sys.argv[1:]
    results = []
    for m in MUTATIONS:
        if only and not any(o in m[0] for o in only):
            continue
        res = run(*m)
        print(f"{res[1]:>12}  {res[0]} {res[2]}", flush=True)
        results.append(res)
    bad = [r for r in results if r[1] != "killed"]
    print(f"\n{len(results) - len(bad)}/{len(results)} killed")
    for r in bad:
        print("  NOT KILLED:", r[0], r[2])
