"""Mutation-test every behavior phase 2 of the eval-splits project claims to cover.

Apply a mutation to the source, run the tests named for it, restore the source. A mutation
that SURVIVES means no test discriminates that line, which is the failure this phase kept
producing (see phase_plans/phase_2.md). Run from anywhere:

    uv run --frozen python specs/projects/eval_splits_v1_v2/phase2_mutation_sweep.py

Pass substrings to run a subset. Expected result: every mutation killed.
"""

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]

EVAL = "libs/core/kiln_ai/datamodel/eval.py"
SPLITS = "libs/core/kiln_ai/datamodel/eval_splits.py"
API = "app/desktop/studio_server/eval_api.py"

DM = "libs/core/kiln_ai/datamodel/test_eval_model.py"
DS = "libs/core/kiln_ai/datamodel/test_eval_splits.py"
TAPI = "app/desktop/studio_server/test_eval_api.py"

MUTATIONS = [
    (
        "migration: splits not populated",
        EVAL,
        "                self.splits[name] = TaskRunSplit(filter_id=filter_id)",
        "                pass",
        DM,
    ),
    (
        "migration: splits precedence dropped (legacy overwrites)",
        EVAL,
        "            if filter_id is not None and name not in self.splits:",
        "            if filter_id is not None:",
        DM,
    ),
    (
        "migration: legacy fields not cleared",
        EVAL,
        "            self.__dict__[field_name] = None\n        return self",
        "        return self",
        DM,
    ),
    (
        "migration: fields-set marking removed",
        EVAL,
        "                # carry it: on a legacy eval `splits` was never explicitly set.\n"
        '                self.__pydantic_fields_set__.add("splits")',
        "                pass",
        DM,
    ),
    (
        "migration: train has no legacy field",
        EVAL,
        '    "train": "train_set_filter_id",\n',
        "",
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
        "shim: does not populate splits",
        EVAL,
        '            splits["test"] = {"source": "eval_input", "filter_id": filter_id}',
        "            pass",
        DM,
    ),
    (
        "shim: splits precedence dropped",
        EVAL,
        '        if "test" not in splits:',
        "        if True:",
        DM,
    ),
    # Eight entries lived here, all mutating Eval's wrap serializer
    # (serialize_preserving_split_format) and the __get_pydantic_json_schema__ override
    # that existed to undo its effect on the OpenAPI schema: the legacy-field-present
    # check, the provenance test, the empty-splits-key deletion, the legacy-field write,
    # the schema override, the two set_split homing branches, and the run-once guard on
    # the fold. All of that machinery is deleted — splits have one home, the legacy
    # fields are cleared as they are migrated, and Eval has no model serializer at all —
    # so there are no lines left to mutate. The behaviors that replaced them are the
    # "migration:" entries above. Left as a note rather than deleted silently, because a
    # PATTERN-MISS on a re-run would otherwise read as a regression.
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
        "        # built by model_construct, where nothing did.\n"
        '        self.__pydantic_fields_set__.add("splits")',
        "        pass",
        DM,
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
        '        case None:\n            return ResolvedSplit(name=split, source="task_run", items=[], eval_id=eval.id)',
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
    # Two entries lived here — "runner: source mode never eval_input" and "runner:
    # task_run_eval ignores the split's filter". Phase 4 deleted both target lines: the
    # runner no longer has an eval-level source mode and no longer resolves a filter, it
    # is handed a ResolvedSplit. Left as a note rather than deleted silently, because a
    # PATTERN-MISS on a re-run would otherwise read as a regression. The equivalent
    # behaviors are covered by phase4_mutation_sweep.py's "collect_tasks_for_task_run_eval:
    # iterates the task's runs, not the split" and its dedupe-source entries.
    #
    # A third entry lived here — "update endpoint: direct splits write instead of
    # set_split". Its pattern still matches, but with one home set_split and
    # `eval.splits[...] = ...` differ only in the readonly guard and the exclude_unset
    # marking, neither of which this endpoint's tests can observe (it never holds a
    # readonly eval, and never dumps with exclude_unset). Both are mutated directly on
    # set_split above. Kept as a note so its absence doesn't read as a gap.
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
        "migration: golden migrated in as a split",
        EVAL,
        "            self.__dict__[field_name] = None\n        return self",
        "            self.__dict__[field_name] = None\n"
        "        if self.eval_configs_filter_id is not None:\n"
        '            self.splits["golden"] = TaskRunSplit(filter_id=self.eval_configs_filter_id)\n'
        "        return self",
        DM + " " + DS,
    ),
    (
        "migration: train-split minting re-introduced",
        EVAL,
        "            self.__dict__[field_name] = None\n        return self",
        "            self.__dict__[field_name] = None\n"
        '        if "train" not in self.splits:\n'
        '            self.splits["train"] = TaskRunSplit(\n'
        '                filter_id="tag::train_" + self.name.lower().replace(" ", "_")\n'
        "            )\n"
        "        return self",
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
                # --frozen: a bare `uv run` re-resolves and can rewrite the lockfile
                # mid-sweep, which has corrupted the venv in a sandboxed run before.
                "--frozen",
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
    # Exit nonzero when anything survived. Without this the sweep reports SURVIVED
    # and PATTERN-MISS and still exits 0, so a caller reading only the status sees a
    # clean sweep and a hollowed-out one as identical.
    raise SystemExit(1 if bad else 0)
