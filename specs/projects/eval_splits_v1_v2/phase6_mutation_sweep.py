"""Mutation-test every behavior phase 6 of the eval-splits project claims to cover.

Same harness as phase2/phase3/phase4_mutation_sweep.py: each mutation applies one
or more textual edits to the tree, runs a test file, and expects it to fail. Run from
anywhere:

    uv run python specs/projects/eval_splits_v1_v2/phase6_mutation_sweep.py

Pass substrings to run a subset. Expected result: every mutation killed.

Web-side behavior (the TS fold, the SSE reader) is covered by vitest rather than pytest,
so it is not in this harness; see phase_plans/phase_6.md's Tests section for those.
"""

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]

API = "app/desktop/studio_server/eval_api.py"
TAPI = "app/desktop/studio_server/test_eval_api.py"

MUTATIONS = [
    # -- results are scoped to exactly one split (functional spec 5) ----------
    (
        "get_eval_run_results: the split parameter is optional again",
        [
            (
                API,
                "        split: Annotated[\n            EvalSplitName,",
                "        split: Annotated[\n            EvalSplitName | None,",
            ),
            (
                API,
                '                "split, and reading has no obvious default the way running does."\n            ),\n        ],',
                '                "split, and reading has no obvious default the way running does."\n            ),\n        ] = None,',
            ),
            (
                API,
                "        resolved_split = resolved_split_or_422(task, eval, split)",
                '        resolved_split = resolved_split_or_422(task, eval, split or "test")',
            ),
        ],
        TAPI,
    ),
    (
        # The regression the required parameter exists to prevent: a mixed-split
        # table that looks exactly like a correct one.
        "get_eval_run_results: returns every run, unscoped by split",
        [
            (
                API,
                "            if run_result.task_run_config_id == run_config_id\n            and eval_run_item_key(run_result) in resolved_split",
                "            if run_result.task_run_config_id == run_config_id",
            )
        ],
        TAPI,
    ),
    (
        "get_eval_run_results: runs the requested split's name but reads test",
        [
            (
                API,
                "        resolved_split = resolved_split_or_422(task, eval, split)",
                '        resolved_split = resolved_split_or_422(task, eval, "test")',
            )
        ],
        TAPI,
    ),
    (
        # Both stores draw ids from one 12-digit generator (functional spec 5.3).
        "get_eval_run_results: membership keyed on the bare id",
        [
            (
                API,
                "            and eval_run_item_key(run_result) in resolved_split",
                "            and eval_run_item_key(run_result)[1]\n            in {key[1] for key in resolved_split.item_keys()}",
            )
        ],
        TAPI,
    ),
    # -- progress reports every split's real size (functional spec 6.1) ------
    (
        "get_eval_progress: val size is reported as train's",
        [
            (
                API,
                "            val_dataset_size=split_size(val_split),",
                "            val_dataset_size=split_size(train_split),",
            )
        ],
        TAPI,
    ),
    (
        "get_eval_progress: an absent split is reported as its test size",
        [
            (
                API,
                "    return len(split) if split is not None else 0",
                "    return len(split) if split is not None else 1",
            )
        ],
        TAPI,
    ),
    (
        # The 400 this phase deleted. It refused every EvalInput-backed eval,
        # which is the expected V2 state rather than an error.
        "get_eval_progress: refuses an eval with no legacy test field",
        [
            (
                API,
                '        test_split = resolved_split_or_422(task, eval, "test")\n        train_split',
                '        if eval.eval_set_filter_id is None:\n            raise HTTPException(status_code=400, detail="unsupported")\n        test_split = resolved_split_or_422(task, eval, "test")\n        train_split',
            )
        ],
        TAPI,
    ),
    # -- summaries aggregate over one split, in one store (spec 5, 5.3) ------
    (
        "compute_score_summary: expected items keyed on the bare id",
        [
            (
                API,
                "    split_items = split.item_keys()",
                "    split_items = {key[1] for key in split.item_keys()}",
            ),
            (
                API,
                "        item_key = eval_run_item_key(eval_run)\n        if item_key not in remaining_expected_items[run_config_id]:",
                "        item_key = eval_run_item_key(eval_run)[1]\n        if item_key not in remaining_expected_items[run_config_id]:",
            ),
        ],
        TAPI,
    ),
    (
        "compute_score_summary: counts a run whose item left the split",
        [
            (
                API,
                "        item_key = eval_run_item_key(eval_run)\n        if item_key not in remaining_expected_items[run_config_id]:\n            continue\n        else:\n            remaining_expected_items[run_config_id].remove(item_key)",
                "        item_key = eval_run_item_key(eval_run)\n        remaining_expected_items[run_config_id].discard(item_key)",
            )
        ],
        TAPI,
    ),
    (
        "get_eval_config_score_summary: refuses an eval with no legacy test field",
        [
            (
                API,
                '        test_split = resolved_split_or_422(task, eval, "test")\n        if len(test_split) == 0:',
                '        test_split = resolved_split_or_422(task, eval, "test")\n        if eval.eval_set_filter_id is None or len(test_split) == 0:',
            )
        ],
        TAPI,
    ),
    (
        "get_run_config_eval_scores: membership keyed on the bare id",
        [
            (
                API,
                "            remaining_expected_items = test_split.item_keys()",
                "            remaining_expected_items = {\n                key[1] for key in test_split.item_keys()\n            }",
            ),
            (
                API,
                "                item_key = eval_run_item_key(eval_run)",
                "                item_key = eval_run_item_key(eval_run)[1]",
            ),
        ],
        TAPI,
    ),
    (
        "get_run_config_eval_scores: skips an eval with no legacy test field",
        [
            (
                API,
                '            test_split = resolve_split(task, eval, "test")\n            if test_split is None:',
                '            test_split = resolve_split(task, eval, "test")\n            if test_split is None or eval.eval_set_filter_id is None:',
            )
        ],
        TAPI,
    ),
    # -- the summary cache is source-aware (functional spec 5.3) -------------
    (
        "_cached_test_split: keyed on the filter id alone, ignoring the store",
        [
            (
                API,
                "    key = (split_ref.source, split_ref.filter_id)",
                '    key = ("task_run", split_ref.filter_id)',
            )
        ],
        TAPI,
    ),
    (
        "_cached_test_split: a cache hit keeps the eval it was first resolved for",
        [
            (
                API,
                "    return cached if cached.eval_id == eval.id else replace(cached, eval_id=eval.id)",
                "    return cached",
            )
        ],
        TAPI,
    ),
    (
        "_cached_test_split: resolves once per eval, defeating the cache",
        [
            (
                API,
                "    cached = cache.get(key)",
                "    cached = None",
            )
        ],
        TAPI,
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
