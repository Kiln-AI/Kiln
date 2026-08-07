"""Mutation-test every behavior phase 2 of the eval-splits project claims to cover.

Apply a mutation to the source, run the tests named for it, restore the source. A mutation
that SURVIVES means no test discriminates that line, which is the failure this phase kept
producing (see phase_plans/phase_2.md). Run from anywhere:

    uv run python specs/projects/eval_splits_v1_v2/phase2_mutation_sweep.py

Pass substrings to run a subset. Expected result: every mutation killed.
"""

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]

EVAL = "libs/core/kiln_ai/datamodel/eval.py"
SPLITS = "libs/core/kiln_ai/datamodel/eval_splits.py"
RUNNER = "libs/core/kiln_ai/adapters/eval/eval_runner.py"
API = "app/desktop/studio_server/eval_api.py"

DM = "libs/core/kiln_ai/datamodel/test_eval_model.py"
DS = "libs/core/kiln_ai/datamodel/test_eval_splits.py"
TR = "libs/core/kiln_ai/adapters/eval/test_eval_runner.py"
TAPI = "app/desktop/studio_server/test_eval_api.py"

MUTATIONS = [
    (
        "fold: run-once guard removed",
        EVAL,
        "        if self._legacy_homed_splits is not None:\n            return self\n\n        homed: Set[str] = set()",
        "        homed: Set[str] = set()",
        DM,
    ),
    (
        "fold: test branch does not populate splits",
        EVAL,
        '            self.splits["test"] = TaskRunSplit(filter_id=self.eval_set_filter_id)\n            homed.add("test")',
        '            homed.add("test")',
        DM,
    ),
    (
        "fold: train branch removed",
        EVAL,
        '        if self.train_set_filter_id is not None:\n            self.splits["train"] = TaskRunSplit(filter_id=self.train_set_filter_id)\n            homed.add("train")',
        "        pass",
        DM,
    ),
    (
        "fold: test provenance not recorded",
        EVAL,
        '            self.splits["test"] = TaskRunSplit(filter_id=self.eval_set_filter_id)\n            homed.add("test")',
        '            self.splits["test"] = TaskRunSplit(filter_id=self.eval_set_filter_id)',
        DM,
    ),
    (
        "validate_splits: raise disabled",
        EVAL,
        '        if "test" not in self.splits:',
        "        if False:",
        DM,
    ),
    (
        "shim: both-inputs raise removed",
        EVAL,
        '        if data.get("eval_set_filter_id") is not None:',
        "        if False:",
        DM,
    ),
    (
        "shim: does not fold into splits",
        EVAL,
        '        splits["test"] = {"source": "eval_input", "filter_id": filter_id}',
        "        pass",
        DM,
    ),
    (
        "serializer: legacy-field-present check removed",
        EVAL,
        "                legacy_field is not None\n                and legacy_field in data",
        "                legacy_field is not None",
        DM,
    ),
    (
        "serializer: provenance ignored",
        EVAL,
        "                and (homed is None or name in homed)",
        "",
        DM,
    ),
    (
        "serializer: empty splits key retained",
        EVAL,
        '            if splits_remainder:\n                data["splits"] = splits_remainder\n            else:\n                del data["splits"]',
        '            data["splits"] = splits_remainder',
        DM,
    ),
    (
        "serializer: legacy fields never written",
        EVAL,
        "            if field_name in data:\n                data[field_name] = legacy_values[name]",
        "            pass",
        DM,
    ),
    (
        "json schema override removed",
        EVAL,
        "        return handler(_without_model_serializer(core_schema))",
        "        return handler(core_schema)",
        DM,
    ),
    (
        "set_split: readonly guard removed",
        EVAL,
        '        self._ensure_not_readonly("splits")\n        self.splits[name] = split',
        "        self.splits[name] = split",
        DM,
    ),
    (
        "set_split: fields-set marking removed",
        EVAL,
        '        self.__pydantic_fields_set__.add("splits")',
        "        pass",
        DM,
    ),
    (
        "set_split: homing unconditional",
        EVAL,
        "        if name in LEGACY_SPLIT_FIELDS and isinstance(split, TaskRunSplit):",
        "        if True:",
        DM + " " + TAPI,
    ),
    (
        "set_split: homing never applied",
        EVAL,
        "        if name in LEGACY_SPLIT_FIELDS and isinstance(split, TaskRunSplit):",
        "        if False:",
        DM + " " + TAPI,
    ),
    (
        "TaskRunSplit: extra=allow removed",
        EVAL,
        '    model_config = ConfigDict(extra="allow")\n\n    source: Literal["task_run"] = "task_run"',
        '    source: Literal["task_run"] = "task_run"',
        DM,
    ),
    (
        "EvalInputSplit: extra=allow removed",
        EVAL,
        '    model_config = ConfigDict(extra="allow")\n\n    source: Literal["eval_input"] = "eval_input"',
        '    source: Literal["eval_input"] = "eval_input"',
        DM,
    ),
    (
        "EvalInputSplit: filter type widened to DatasetFilterId",
        EVAL,
        '    source: Literal["eval_input"] = "eval_input"\n    filter_id: EvalInputFilterId',
        '    source: Literal["eval_input"] = "eval_input"\n    filter_id: DatasetFilterId',
        DM,
    ),
    (
        "resolve_split: absent split returns empty instead of None",
        SPLITS,
        "        case None:\n            return None",
        '        case None:\n            return ResolvedSplit(name=split, source="task_run", items=[])',
        DS,
    ),
    (
        "resolve_split: task_run arm reads the wrong store",
        SPLITS,
        "                items=[run for run in task.runs(readonly=True) if task_run_filter(run)],",
        "                items=list(task.eval_inputs(readonly=True)),",
        DS,
    ),
    (
        "ResolvedSplit: membership ignores source",
        SPLITS,
        "    def __contains__(self, key: ItemKey) -> bool:\n        return key in self._item_keys",
        "    def __contains__(self, key: ItemKey) -> bool:\n        return key[1] in {k[1] for k in self._item_keys}",
        DS,
    ),
    (
        "ResolvedSplit: item_keys exposes the internal set",
        SPLITS,
        "    def item_keys(self) -> Set[ItemKey]:\n        return set(self._item_keys)",
        "    def item_keys(self) -> Set[ItemKey]:\n        return self._item_keys",
        DS,
    ),
    (
        "eval_run_item_key: eval_input mislabelled as task_run",
        SPLITS,
        '        return ("eval_input", eval_run.eval_input_id)',
        '        return ("task_run", eval_run.eval_input_id)',
        DS,
    ),
    (
        "runner: source mode never eval_input",
        RUNNER,
        '        if isinstance(target_eval.splits.get("test"), EvalInputSplit):',
        "        if False:",
        TR,
    ),
    (
        "runner: task_run_eval ignores the split's filter",
        RUNNER,
        "        filter = dataset_filter_from_id(test_split.filter_id)",
        '        filter = dataset_filter_from_id("all")',
        TR,
    ),
    (
        "update endpoint: direct splits write instead of set_split",
        API,
        '            eval.set_split("train", TaskRunSplit(filter_id=request.train_set_filter_id))',
        '            eval.splits["train"] = TaskRunSplit(filter_id=request.train_set_filter_id)',
        TAPI,
    ),
    (
        "update endpoint: already-set check reads legacy field",
        API,
        '            if eval.splits.get("train") is not None:',
        "            if eval.train_set_filter_id is not None:",
        TAPI,
    ),
    # Two entries lived here — "judge guard: v2 rejection removed" and "judge worker:
    # guard call removed". Both mutated the judge-feedback-batch surface
    # (judge_feedback_batch_api.py and jobs/workers/judge_feedback_batch.py), which is the
    # draft #1517 branch's code and does not exist on scosman/evals_v2. They pinned this
    # phase's carried-over phase-1 review follow-up — the V2-judge 422 across all four
    # callers of validate_judge_eval — and that follow-up is not in this tree either, so
    # there is nothing here for them to test. Left as a note rather than deleted silently,
    # because a PATTERN-MISS on a re-run would otherwise read as a regression. They belong
    # with the judge-feedback-batch work wherever it lands.
    (
        "fold: golden folded in as a split",
        EVAL,
        "        self._legacy_homed_splits = homed\n        return self",
        '        if self.eval_configs_filter_id is not None:\n            self.splits["golden"] = TaskRunSplit(filter_id=self.eval_configs_filter_id)\n        self._legacy_homed_splits = homed\n        return self',
        DM + " " + DS,
    ),
    (
        "fold: train-split minting re-introduced",
        EVAL,
        "        self._legacy_homed_splits = homed\n        return self",
        '        if "train" not in self.splits:\n            self.splits["train"] = TaskRunSplit(\n                filter_id="tag::train_" + self.name.lower().replace(" ", "_")\n            )\n        self._legacy_homed_splits = homed\n        return self',
        DM,
    ),
]


def run(label, path, old, new, tests):
    f = REPO / path
    original = f.read_text()
    if original.count(old) != 1:
        return label, "PATTERN-MISS", f"(count={original.count(old)})"
    f.write_text(original.replace(old, new))
    try:
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
        f.write_text(original)


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
