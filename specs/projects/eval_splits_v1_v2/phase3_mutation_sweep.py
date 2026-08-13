"""Mutation-test every behavior phase 3 of the eval-splits project claims to cover.

Same harness as phase2_mutation_sweep.py: apply a mutation to the source, run the tests
named for it, restore the source. A mutation that SURVIVES means no test discriminates
that line. Run from anywhere:

    uv run python specs/projects/eval_splits_v1_v2/phase3_mutation_sweep.py

Pass substrings to run a subset. Expected result: every mutation killed.
"""

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]

SPEC_UTILS = "libs/server/kiln_server/utils/spec_utils.py"
SPEC_API = "libs/server/kiln_server/spec_api.py"
COPILOT_API = "app/desktop/studio_server/copilot_api.py"
PO_API = "app/desktop/studio_server/prompt_optimization_job_api.py"

TSU = "libs/server/kiln_server/utils/test_spec_utils.py"
TSA = "libs/server/kiln_server/test_spec_api.py"
TCA = "app/desktop/studio_server/test_copilot_api.py"
TPO = "app/desktop/studio_server/test_prompt_optimization_job_api.py"

MUTATIONS = [
    (
        "spec_eval_splits: no val split",
        SPEC_UTILS,
        '        "val": TaskRunSplit(filter_id=tag_filter_id(val_tag)),\n',
        "",
        TSU + " " + TSA + " " + TCA,
    ),
    (
        "spec_eval_splits: test split points at the train tag",
        SPEC_UTILS,
        '        "test": TaskRunSplit(filter_id=tag_filter_id(eval_tag)),',
        '        "test": TaskRunSplit(filter_id=tag_filter_id(train_tag)),',
        TSU + " " + TSA + " " + TCA,
    ),
    (
        # EvalInputSplit is resolved inline rather than named directly: spec_utils.py does
        # not import it, so the obvious spelling would be killed by a NameError instead of
        # by the isinstance assertion this mutation exists to check.
        "spec_eval_splits: val split is EvalInput-backed",
        SPEC_UTILS,
        '        "val": TaskRunSplit(filter_id=tag_filter_id(val_tag)),',
        '        "val": __import__("kiln_ai.datamodel.eval", fromlist=["EvalInputSplit"]).EvalInputSplit(filter_id=tag_filter_id(val_tag)),',
        TSU + " " + TSA + " " + TCA,
    ),
    (
        "tag_filter_id: no tag:: prefix",
        SPEC_UTILS,
        '    return f"tag::{tag}"',
        "    return tag",
        TSU + " " + TSA,
    ),
    # Three entries lived here, all mutating `set_spec_eval_splits` in spec_utils.py: the
    # direct-dict-assignment, homes-test-only, and does-nothing shapes. That function
    # existed to move a new spec eval's test and train splits into their legacy flat
    # fields; splits now have exactly one home (`Eval.splits`), the legacy fields are
    # cleared as they are migrated in and never written back, so re-setting the splits the
    # eval was constructed with was a no-op and the function is deleted. A fourth entry,
    # "build_spec_eval: splits never homed", mutated its call site and is gone with it.
    # What remains load-bearing — that build_spec_eval constructs the eval *with* its
    # splits — is covered by "build_spec_eval: eval built with no splits at all" below.
    # Left as a note rather than deleted silently, because a PATTERN-MISS on a re-run
    # would otherwise read as a regression.
    # The construction sequence lives in build_spec_eval rather than being duplicated in
    # the two creation paths, so these three are mutated once each. They are run against
    # both API test files as well as the factory's own, which is what shows both paths
    # still go through it — a path that inlined its own construction would survive.
    (
        # Golden is not a split, so nothing in the splits assertions covers it. Pointing
        # it at the test tag would score eval-config comparison against test items
        # instead of golden ones.
        "build_spec_eval: golden filter id from the eval tag",
        SPEC_UTILS,
        "        eval_configs_filter_id=tag_filter_id(tags.golden_tag),",
        "        eval_configs_filter_id=tag_filter_id(tags.eval_tag),",
        TSU + " " + TSA + " " + TCA,
    ),
    (
        # What is load-bearing is that the eval carries its splits at construction:
        # validate_splits requires a test split, and `splits` is the only place any of
        # them is stored.
        "build_spec_eval: eval built with no splits at all",
        SPEC_UTILS,
        "        splits=widened_splits,",
        "        splits={},",
        TSU + " " + TSA + " " + TCA,
    ),
    (
        # The factory returns the tags so the copilot can tag the runs it generates; a
        # mix-up here puts generated items in the wrong split's dataset.
        "copilot_api: generated runs tagged with the train tag as the test tag",
        COPILOT_API,
        "            eval_tag=tags.eval_tag,",
        "            eval_tag=tags.train_tag,",
        TCA,
    ),
    (
        "has_task_run_train_split: any train split counts",
        PO_API,
        '    return isinstance(eval.splits.get("train"), TaskRunSplit)',
        '    return eval.splits.get("train") is not None',
        TPO,
    ),
    (
        "has_task_run_train_split: always False",
        PO_API,
        '    return isinstance(eval.splits.get("train"), TaskRunSplit)',
        "    return False",
        TPO,
    ),
    (
        "has_task_run_train_split: always True",
        PO_API,
        '    return isinstance(eval.splits.get("train"), TaskRunSplit)',
        "    return True",
        TPO,
    ),
    # The four check_eval return sites, each mutated back to the pre-phase implementation
    # rather than to a hardcoded constant: "one site left un-migrated" is the plausible
    # defect, and it is strictly stronger here, since these test evals carry their splits
    # in `splits` and so read None from the legacy field. Each site's test asserts both a
    # True and a False case (sites 1, 2 and 4 via TRAIN_SPLIT_CASES, site 3 via its
    # missing-name / missing-provider pair), so an inverted site is caught as well.
    (
        "check_eval: no-config return left un-migrated",
        PO_API,
        "                    has_default_config=False,\n                    has_train_set=has_task_run_train_split(eval),\n                    model_is_supported=False,\n                )\n\n            # Try to load the current config",
        "                    has_default_config=False,\n                    has_train_set=bool(eval.train_set_filter_id),\n                    model_is_supported=False,\n                )\n\n            # Try to load the current config",
        TPO,
    ),
    (
        "check_eval: config-not-found return left un-migrated",
        PO_API,
        "            except HTTPException:\n                return CheckEvalResponse(\n                    has_default_config=False,\n                    has_train_set=has_task_run_train_split(eval),",
        "            except HTTPException:\n                return CheckEvalResponse(\n                    has_default_config=False,\n                    has_train_set=bool(eval.train_set_filter_id),",
        TPO,
    ),
    (
        "check_eval: config-not-found return inverted",
        PO_API,
        "            except HTTPException:\n                return CheckEvalResponse(\n                    has_default_config=False,\n                    has_train_set=has_task_run_train_split(eval),",
        "            except HTTPException:\n                return CheckEvalResponse(\n                    has_default_config=False,\n                    has_train_set=True,",
        TPO,
    ),
    (
        "check_eval: missing-model return left un-migrated",
        PO_API,
        "                    has_default_config=True,\n                    has_train_set=has_task_run_train_split(eval),\n                    model_is_supported=False,",
        "                    has_default_config=True,\n                    has_train_set=bool(eval.train_set_filter_id),\n                    model_is_supported=False,",
        TPO,
    ),
    (
        "check_eval: success return left un-migrated",
        PO_API,
        "                has_train_set=has_task_run_train_split(eval),\n                model_is_supported=response.is_model_supported,",
        "                has_train_set=bool(eval.train_set_filter_id),\n                model_is_supported=response.is_model_supported,",
        TPO,
    ),
    # The guard's *placement* before packaging is not in this list, because moving the call
    # is not a single contiguous replacement — it is a deletion here plus an insertion ~30
    # lines away, and this harness applies one edit. It is covered by
    # mock_package.assert_not_called() in the refusal test, confirmed by hand-moving the
    # call to after package_project_for_training and watching that assertion fail. An
    # earlier version of this file listed that as a mutation; it deleted the call rather
    # than moving it, so it was a duplicate of the entry below.
    (
        "start job: train-split guard removed",
        PO_API,
        "        reject_unusable_train_splits(task, request.eval_ids)",
        "        pass",
        TPO,
    ),
    (
        # Drops the presence clause, so an eval with no train split is refused too. The
        # complementary narrowing — naming EvalInputSplit explicitly instead of "not
        # TaskRun-backed" — is deliberately absent: it is an equivalent mutant while
        # EvalInputSplit is the only other SplitRef variant, and the closed phrasing is
        # there for the variant that does not exist yet.
        "start job: guard refuses an absent train split too",
        PO_API,
        "        if has_train_split and not has_task_run_train_split(eval):",
        "        if not has_task_run_train_split(eval):",
        TPO,
    ),
    (
        "start job: unknown eval ids fall through to another eval",
        PO_API,
        "        if eval is None:\n            continue",
        "        if eval is None:\n            eval = next(iter(evals_by_id.values()), None)\n        if eval is None:\n            continue",
        TPO,
    ),
    (
        "start job: guard checks every eval on the task, not the requested ones",
        PO_API,
        "    for eval_id in eval_ids:",
        "    for eval_id in evals_by_id:",
        TPO,
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
