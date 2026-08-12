"""Mutation-test every behavior phase 4 of the eval-splits project claims to cover.

Same harness as phase2/phase3_mutation_sweep.py, with one addition: a mutation may apply
several edits at once. Phase 4's headline change is a *deletion* whose effect is only
observable together with the routing that used to reach it, so re-inserting the deleted
branch alone mutates unreachable code and could never be killed. Run from anywhere:

    uv run python specs/projects/eval_splits_v1_v2/phase4_mutation_sweep.py

Pass substrings to run a subset. Expected result: every mutation killed.

One mutation removed on the evals_v2 rebuild
--------------------------------------------

The original sweep carried a thirteenth mutation, "worker: builds the runner over an
empty split", which rewrote `jobs/workers/eval.py`'s `resolve_split` call to hand the
runner an empty `ResolvedSplit` and expected `jobs/workers/test_eval.py` to catch it. The
jobs layer's eval worker does not exist on `scosman/evals_v2` — it belongs to the draft
#1517 branch this project was first built against — so neither the file it mutates nor
the test that killed it is in this tree. It is removed rather than re-targeted: nothing
here plays the worker's role, and the runner-side and eval_api-side behaviors it depended
on are already covered by the mutations above. It comes back with the worker; see
implementation_plan.md's phase 5 entry for where that work went.
"""

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]

RUNNER = "libs/core/kiln_ai/adapters/eval/eval_runner.py"
SPLITS = "libs/core/kiln_ai/datamodel/eval_splits.py"
EVAL_API = "app/desktop/studio_server/eval_api.py"

TRUNNER = "libs/core/kiln_ai/adapters/eval/test_eval_runner.py"
TSPLITS = "libs/core/kiln_ai/datamodel/test_eval_splits.py"
TEVAL_API = "app/desktop/studio_server/test_eval_api.py"

# The EvalInput/eval_config_eval branch of _run_v2_job as it stood before this phase.
RESTORED_CALIBRATION_BRANCH = """        if isinstance(job.item, EvalInput):
            if job.type == "eval_config_eval":
                async with self._save_context():
                    eval_run = EvalRun(
                        parent=job.eval_config,
                        task_run_config_id=None,
                        dataset_id=None,
                        eval_input_id=job.item.id,
                        eval_config_eval=True,
                        scores={},
                        input=early_input_str,
                        output=None,
                        skipped_reason=SkippedReason.incompatible_input_shape.value,
                        skipped_detail="EvalInput source has no stored output",
                    )
                    eval_run.save_to_file()
                return True
"""

MUTATIONS = [
    # -- the constructor's two guards (architecture 4.2) -----------------------
    (
        "init: task_run_eval no longer requires a split",
        [
            (
                RUNNER,
                '            if split is None:\n                raise ValueError("Task run eval requires a resolved split")',
                "            pass",
            )
        ],
        TRUNNER,
    ),
    (
        "init: eval_config_eval accepts a split",
        [
            (
                RUNNER,
                "            if split is not None:\n                raise ValueError(\n                    \"Mode 'eval_config_eval' does not support a split: it is scoped by the eval's golden filter\"\n                )",
                "            pass",
            )
        ],
        TRUNNER,
    ),
    # -- collect_tasks dispatch (architecture 4.1) ----------------------------
    (
        "collect_tasks: task_run_eval routed to the golden filter",
        [
            (
                RUNNER,
                '        if self.eval_run_type == "eval_config_eval":',
                "        if self.eval.eval_configs_filter_id is not None:",
            )
        ],
        TRUNNER,
    ),
    (
        # The whole EvalInput calibration path restored: the mis-routing plus the branch
        # that papered over it. Neither half is observable alone — with the branch gone the
        # mis-routing errors out instead of writing records, and with the routing gone the
        # branch is unreachable. Architecture 4.3 is a claim about the pair.
        "eval_config_eval: EvalInput calibration path restored",
        [
            (
                RUNNER,
                "        for task_run in self.task.runs(readonly=True)\n            if filter(task_run)",
                "        for task_run in self.task.eval_inputs(readonly=True)\n            if True",
            ),
            (
                RUNNER,
                "        if isinstance(job.item, EvalInput):\n",
                RESTORED_CALIBRATION_BRANCH,
            ),
        ],
        TRUNNER,
    ),
    (
        "eval_config_eval: golden filter ignored",
        [(RUNNER, "            if filter(task_run)", "            if True")],
        TRUNNER,
    ),
    # -- the split is the item scope ------------------------------------------
    (
        "collect_tasks_for_task_run_eval: iterates the task's runs, not the split",
        [
            (
                RUNNER,
                "            for item in self.split.items",
                "            for item in self.task.runs(readonly=True)",
            )
        ],
        TRUNNER,
    ),
    # -- dedupe keys on ItemKey (architecture 3.1) ----------------------------
    (
        "dedupe: keyed on the bare id instead of the ItemKey",
        [
            (
                RUNNER,
                "                    already_run[eval_config.id][run.task_run_config_id].add(\n                        eval_run_item_key(run)\n                    )",
                "                    already_run[eval_config.id][run.task_run_config_id].add(\n                        eval_run_item_key(run)[1]\n                    )",
            ),
            (
                RUNNER,
                "            if (self.split.source, item.id)\n            not in already_run[eval_config.id][run_config.id]",
                "            if item.id not in already_run[eval_config.id][run_config.id]",
            ),
        ],
        TRUNNER,
    ),
    (
        "dedupe: the item's source is hardcoded to task_run",
        [
            (
                RUNNER,
                "            if (self.split.source, item.id)",
                '            if ("task_run", item.id)',
            )
        ],
        TRUNNER,
    ),
    (
        "dedupe: dropped entirely",
        [
            (
                RUNNER,
                "            if (self.split.source, item.id)\n            not in already_run[eval_config.id][run_config.id]",
                "            if True",
            )
        ],
        TRUNNER,
    ),
    (
        "dedupe: crosses run configs",
        [
            (
                RUNNER,
                "                if (\n                    run.task_run_config_id is not None\n                    and run.task_run_config_id in already_run[eval_config.id]\n                ):\n                    already_run[eval_config.id][run.task_run_config_id].add(",
                "                if True:\n                    already_run[eval_config.id][run.task_run_config_id] = set()\n                for _rc_id in already_run[eval_config.id]:\n                    already_run[eval_config.id][_rc_id].add(",
            )
        ],
        TRUNNER,
    ),
    (
        "dedupe: includes runs from other run configs",
        [
            (
                RUNNER,
                "                    and run.task_run_config_id in already_run[eval_config.id]\n",
                "",
            )
        ],
        TRUNNER,
    ),
    (
        # The `is not None` is not redundant with the membership test: ID_TYPE is
        # `str | None`, and a run config with a null id makes None a real key.
        "dedupe: run configs with a null id absorb the calibration records",
        [
            (
                RUNNER,
                "                    run.task_run_config_id is not None\n                    and ",
                "                    ",
            )
        ],
        TRUNNER,
    ),
    # -- a split belongs to the eval it was resolved from (architecture 4.2) ---
    (
        "init: any eval's split is accepted",
        [
            (
                RUNNER,
                "            if split.eval_id != target_eval.id:",
                "            if False:",
            )
        ],
        TRUNNER,
    ),
    (
        # Both branches, because the binding check can only be as good as what
        # resolve_split records — and each backing reaches it through a different one.
        "resolve_split: TaskRun-backed splits don't record their eval",
        [
            (
                SPLITS,
                "                items=[run for run in task.runs(readonly=True) if task_run_filter(run)],\n                eval_id=eval.id,",
                '                items=[run for run in task.runs(readonly=True) if task_run_filter(run)],\n                eval_id="",',
            )
        ],
        TRUNNER + " " + TSPLITS,
    ),
    (
        "resolve_split: EvalInput-backed splits don't record their eval",
        [
            (
                SPLITS,
                "                ],\n                eval_id=eval.id,",
                '                ],\n                eval_id="",',
            )
        ],
        TRUNNER + " " + TSPLITS,
    ),
    # -- the golden-set refusal has to beat the StreamingResponse -------------
    (
        "init: no-golden-set check deferred to collect time",
        [
            (
                RUNNER,
                "            if target_eval.eval_configs_filter_id is None:\n                raise ValueError(no_golden_set_message(target_eval))\n",
                "",
            )
        ],
        TRUNNER,
    ),
    (
        "eval_api: calibration golden-set guard removed",
        [(EVAL_API, "        require_golden_set_or_422(eval)", "        pass")],
        TEVAL_API,
    ),
    # -- call sites ------------------------------------------------------------
    (
        "eval_api: the run endpoint resolves the train split",
        [
            (
                EVAL_API,
                '            split=resolved_split_or_422(task, eval, "test"),',
                '            split=resolved_split_or_422(task, eval, "train"),',
            )
        ],
        TEVAL_API,
    ),
    (
        "eval_api: resolved_split_or_422 returns an empty split instead of 422ing",
        [
            (
                EVAL_API,
                "        raise HTTPException(\n            status_code=422,\n            detail=f\"Eval '{eval.id}' has no '{split}' split.\",\n        )",
                '        return ResolvedSplit(name=split, source="task_run", items=[], eval_id=eval.id)',
            )
        ],
        TEVAL_API,
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
    # Exit nonzero when anything survived. Without this the sweep reports SURVIVED
    # and PATTERN-MISS and still exits 0, so a caller reading only the status sees a
    # clean sweep and a hollowed-out one as identical.
    raise SystemExit(1 if bad else 0)
