---
status: complete
---

# Phase 5: Migration

## Overview

The last phase, and the only one that rewrites data a user already has on disk. Phases
1–4 made pointer-mode records writable, readable and protected; this one converts the V2
records written *before* the split into that shape, so internal V2 projects get trace
reuse for the traces they already paid for instead of only for traces generated from here
on.

A new CLI command, `kiln_ai migrate-eval-runs <project>`, over one project directory
(architecture §7). For every `EvalRun` under a V2 `EvalConfig`:

- **inline scored record** → synthesize the `TaskRun` its inline fields describe, save it,
  and rewrite the record to point at it.
- **calibration record** → point `scored_run_id` at `dataset_id`; the golden dataset item
  is already the trace, so nothing is created.
- **skipped before generation** → clear the inline fields, point at nothing.
- **already pointer-mode** → untouched, which is what makes the command idempotent.
- **V1 config** → untouched, entirely (functional spec §7).

### What the data actually looks like

Worth stating, because it shrinks the job: the pre-split V2 runner
(`git show a3fa268~1:.../eval_runner.py`) only ever wrote `input`, `output`,
`reference_data`, `scores`, `intermediate_outputs` and the skip fields on a V2 record.
`task_run_trace`, `task_run_usage` and `reference_answer` were written by the **V1** path
alone. So a real V2 inline record migrates to a `TaskRun` with `trace=None` and
`usage=None`. The migration still carries all five fields, because a record is a file on
disk and this is a one-way rewrite — but no V2 record on disk is expected to exercise the
trace/usage half.

The same source explains one shape that looks wrong and isn't: a V2 record that was
skipped *at scoring time* also has `output=None` (`output=... if skipped_reason is None
else None`). Its trace existed, but the record kept no copy of it, so there is nothing to
reconstruct. It migrates as a skip with no `scored_run_id` — the only lossless option.

### Plan, then apply

The command runs in two passes, and the first one writes nothing:

1. **Plan** — walk the project and build, in memory, every `TaskRun` and every rewritten
   `EvalRun` the migration would save. Both are constructed through their normal
   validators, so a record that cannot migrate (an input that no longer matches the task's
   schema, a deleted run config, a calibration record with no `dataset_id`) is discovered
   here, named, and left alone.
2. **Apply** — save what the plan built. Trace first, then the score record
   (architecture §7): an interruption then leaves an orphan `TaskRun` rather than a score
   pointing at a file that was never written.

   That orphan is *not* free, which is worth stating plainly because the ordering's usual
   justification says it is. It is invisible on dataset surfaces, but since Phase 4 an
   eval-generated run cannot be deleted from the app at all — the 409 keys on the
   `eval_source` stamp, not on being referenced — so a retry that minted a second copy
   would leave a permanent duplicate behind every time. The migration therefore reuses a
   trace already on disk that is *this* generation (`reuse_trace`), which makes the retry
   path idempotent in the trace store and leaves the ordering's real guarantee intact: the
   worst an interruption can do is leave a trace the next run adopts.

`--dry-run` is pass 1 alone. That is the property worth the structure: the dry run is not
a second code path that predicts what the real one would do, it *is* the real one with
the saves withheld, so it can only under-report failures that are disk failures.

Without `--dry-run`, the plan is printed and confirmed before anything is written
(`--yes` skips the prompt for scripted use). Either way the command exits 1 if anything
was left unmigrated — including a dry run, since a preflight is the more likely thing to
script.

### Never clear the last copy

Two of the three write actions *delete* data: `link_calibration` and `clear_inline` drop
the record's inline copy of what it scored and defer to something named by id. Ids are
not references — delete protection covers eval *traces* (architecture §6, D16), not the
golden items and dataset rows an eval record names — so both check that the item still
exists, and refuse if it doesn't. `create_trace` needs no such check: it writes the
replacement itself.

The calibration case is the sharp one. A golden item can be deleted today with nothing to
stop it, and its calibration records are then the only surviving copy of what was scored;
pointing at the deleted item and clearing the copy would destroy it with no way back.

**Asked twice, because once is a snapshot.** The plan-time check reads the whole store
once per task; the write-time check re-reads the one item's own path, immediately before
that record is overwritten. Both are needed: a plan-time check alone is minutes stale by
the time it is acted on, with a confirmation prompt holding it open, and a write-time
check alone would find every refusal after the operator had already said yes.

The second is the *same* question, not a cheaper one: it loads the item and confirms its
id, exactly as the plan did. An existence check would be weaker than its own counterpart,
and observably so — a file written by a newer Kiln (which this command treats as normal
everywhere else) or replaced by a sync carrying a different id is present but is not the
item, and clearing the record's last copy in favour of it destroys that copy silently.

Memory: the plan holds every synthesized trace for the project at once. Accepted — this
is a one-shot command over one internal project, and `EvalConfig.runs()` already
materializes every score record per config. Confirm-before-any-write is worth more here
than streaming.

Two known limits, both recorded rather than fixed:

- **Undeclared fields on disk are dropped.** The rewrite round-trips a record through
  `model_dump()` → `model_validate`, so a field a *newer* Kiln added and this build does
  not declare is gone afterwards. That is what every Kiln save already does; the
  difference is blast radius, since this rewrites every V2 record in a project at once.
  Files this build can't read at all are stepped over rather than rewritten, which covers
  the version-skew case that actually carries a schema change.
- **The plan/apply window is user-length**, because the confirmation prompt sits inside
  it. Mitigated rather than closed: immediately before each write, the record is re-read
  and compared *whole* against what was planned from — any concurrent edit, not just a
  concurrent migration — and the item it defers to is re-loaded and re-identified. Either
  one stale and the change is reported and skipped rather than written.

## Steps

1. **`libs/core/kiln_ai/cli/commands/migrate_eval_runs.py` — new.**

   Classification, pure and total over a record:

   ```python
   class MigrationAction(str, Enum):
       create_trace = "create_trace"        # synthesize the TaskRun, then point at it
       reuse_trace = "reuse_trace"          # that TaskRun is already on disk: point at it
       link_calibration = "link_calibration"  # point at the golden dataset item
       clear_inline = "clear_inline"        # skipped before generation: drop inline fields
       nothing_to_do = "nothing_to_do"      # already pointer-mode, or already clean
       unmigratable = "unmigratable"        # reported, left exactly as it is
   ```

   ```python
   @dataclass(frozen=True)
   class PlannedChange:
       action: MigrationAction
       eval_run: EvalRun                  # the record as it is on disk
       detail: str                        # why, for the report
       trace: TaskRun | None              # synthesized, unsaved
       migrated: EvalRun | None           # rewritten, unsaved
       requires_item: ItemReference | None  # what it defers to, re-checked at the write
   ```

   Order of the branches follows architecture §7 exactly, and the calibration branch sits
   *above* the skip branch on purpose: a calibration record points at the golden item
   whether or not the judge was reached, which is the rule Phase 3 settled for live skips
   (`_calibration_item`). Migrating them any other way would give an old calibration skip
   a different shape than a new one.

   Both clearing branches ask `_required_item`, which resolves the record's
   `eval_run_item_key()` against a `TaskIndex` — one scan per task, answering both "where
   is each dataset item" and "which eval traces already exist" — and refuses a record
   whose item is gone, per "never clear the last copy" above. The same key helper on both
   sides makes "these two check the same thing" visible rather than something the reader
   has to prove. `TaskIndex` is loaded only for a task that has a V2 config, so a project
   with no V2 evals never scans a dataset.

   The resolved `ItemReference` (key plus path) rides along on the `PlannedChange` so the
   write pass can re-check it, by loading *that one path* and confirming the id — not by
   looking the id up again. `from_id_and_parent_path` rescans the whole store per call,
   which with a cold model cache means re-reading every run in the dataset once per
   record; reading the known path is O(1). The path is exact for what this needs —
   `save_to_file` keeps a record where it was loaded from, and `delete()` removes the
   directory it lives in. A moved file reads as missing and refuses the change, which is
   the safe direction.

   That re-read **drops the `ModelCache` entry for the path first**, and that is the point
   of it rather than a detail. The cache validates on mtime alone, and the plan's own
   `readonly=True` scan is what populated it — so a replacement that preserves mtime
   (`rsync -t`, Syncthing, Dropbox and iCloud all do, by design, and "replaced by a sync"
   is the exact scenario this guards) would be served the plan's own parse, and the check
   would confirm the plan against the plan.

   The reuse branch names the trace it found in the same `requires_item`, and also hands
   over the copy it matched (`expected`). Whatever the plan matched on is what the write
   pass re-asks: a dataset item is chosen by id, so an id is all there is to re-check, but
   a reused trace is chosen by its *content*, and re-asking only its id would give that
   guarantee up at the one moment the migration can still refuse while the record's own
   copy is still on disk. Both checks are then the plan's own, not a cheaper relative of
   it — the same principle the mtime paragraph above is about, applied to the other half.

   The id comparison stays in front of the content one rather than being subsumed by it:
   `_same_generation` deliberately ignores a record's own identity fields, so a same-content
   file carrying a new id would pass it while leaving `scored_run_id` pointing at nothing.
   Pinned by a test rather than by this paragraph — a deviation defended only in prose is
   one cleanup away from being reverted.

   A refused reference is reported in the terms it was refused on
   (`_stale_reference_message`). A reuse refused on content is not a missing file — it is
   present and parses fine — and saying otherwise sends an operator looking for a file
   sitting exactly where the message names it.

2. **`migrate_eval_runs.py` — synthesizing the trace.**

   ```python
   def _synthesized_trace(task, eval_run, run_config) -> TaskRun
   ```

   - `input` / `output.output` from the record's inline fields.
   - `trace` from `task_run_trace`, `json.loads`-ed back into the message list it was
     serialized from; `usage` from `task_run_usage`; `cumulative_usage` recomputed with
     `MessageUsage.from_trace`, the same way `generate_run` does.
   - `eval_source` from `eval_run_item_key()` — the same helper the runner and the trace
     index use, so a migrated trace is filed under the identity a later job looks it up
     by.
   - `input_source` and `output.source` are both a `DataSource` built from the record's
     `task_run_config_id` (architecture §7): `synthetic` carrying the run config's
     model/provider for a `kiln_agent` config, `tool_call` for an `mcp` one, mirroring
     `BaseAdapter._properties_for_task_output`. `run_config_id` on it is the half of the
     trace key that makes the trace reusable; `adapter_name` is
     `"kiln_eval_run_migration"`, because the record does not say which adapter ran and
     inventing one would be worse than naming the migration.
   - A record whose `task_run_config_id` names a run config that no longer exists is
     `unmigratable`: a `synthetic` source *requires* a model name, and fabricating one
     writes a lie to disk. Left as a legacy inline record, which still renders.

   The synthesized trace is then offered to `TaskIndex.existing_trace`, which returns a
   trace already on disk that *is* this generation — same trace key, and the same record
   field for field (`TRACE_IDENTITY_EXCLUDES` names the parts a second copy is allowed to
   differ in: its own id and timestamps, on the nested `TaskOutput` too). Identity is
   content, not the key: a trace at the same key holding a *different* output is a
   different generation, and pointing a score at it would claim the judge saw something it
   never saw. Content-identical means reuse is invisible to every reader.

   This is not the deduplication functional spec §8 punts, either: two records only ever
   share a trace when what they scored was byte-identical anyway, and the case it exists
   for is a retry adopting the trace an interrupted run of *this* command already wrote.

3. **`migrate_eval_runs.py` — rewriting the score record.**

   ```python
   def _pointer_record(eval_run, scored_run_id) -> EvalRun
   ```

   Built as a new instance from `eval_run.model_dump()` with the five inline fields
   cleared and `scored_run_id` set, not by assignment. `validate_assignment=True` means
   every intermediate state is validated, and there is no order in which the two halves of
   this change are individually legal: clearing `input` first fails "a legacy EvalRun
   requires input", setting `scored_run_id` first fails "must not carry inline trace
   data". Constructing the end state validates it once, as a whole, before anything is
   written.

4. **`migrate_eval_runs.py` — the walk and the apply.**

   ```python
   def plan_project(project: Project) -> MigrationPlan
   def apply_plan(plan: MigrationPlan) -> list[MigrationFailure]
   ```

   `plan_project` iterates tasks → evals → configs → runs, skipping non-V2 configs
   (counting them for the report). Two layers of tolerance, because neither covers the
   other: every child load goes through `all_children_of_parent_path_with_errors`, so a
   file this build cannot read is reported and stepped over rather than raising out of the
   walk; and every per-record planning step is wrapped, so a record that loads but cannot
   be migrated is reported too. One bad file must not stop a whole project.

   `apply_plan` saves trace then record, per change, and collects failures the same way.
   `_stale_precondition` re-checks both halves of what the plan assumed, per record, right
   before the write: the record is re-read and compared whole (any concurrent edit, not
   only a concurrent migration — an unmodified record's two dumps are exactly equal, so
   there is nothing to be lax about), and the item it defers to must still be there.

5. **`migrate_eval_runs.py` — the command.**

   ```python
   def migrate_eval_runs(project_path, dry_run: bool = False, yes: bool = False) -> None
   ```

   Reuses `package_project.load_project` for the path handling and the
   "here are your projects" error. Prints a counts table — labelled in the future tense,
   since it is a plan in both modes — then either stops (`--dry-run`), confirms, or
   applies. The confirmation names both writes ("Update 4 eval record(s) and create 2 task
   run(s)?") since it is the only gate before a one-way rewrite.

   Every path and reason in the refusal report goes through `rich.markup.escape`. Task
   names may contain square brackets, so every path beneath them does, and a pydantic
   message always ends `[type=..., input_value=...]` — rich would read both as markup and
   eat them, printing a path that resolves to nothing and a reason that stops mid-sentence.
   This is the one surface that tells an operator what a data-safety command refused.

   Exits 1 if anything was unmigratable, unreadable, or failed to save — on a dry run and
   on a declined prompt too, so what the command found doesn't depend on how the operator
   got out of it. Records and files are counted separately in that summary: an unreadable
   dataset file is not an eval record that failed to migrate, and one unreadable golden
   item also makes every calibration record naming it unmigratable, so a single total
   would both mislabel and double-count.

6. **`libs/core/kiln_ai/cli/cli.py`** — register
   `app.command(name="migrate-eval-runs")(migrate_eval_runs.migrate_eval_runs)`.
   Hyphenated, as architecture §7 names it, though the neighbouring `package_project` uses
   an underscore — matching the neighbour would mean diverging from the spec, and renaming
   the neighbour is churn in a shipped command for a one-shot migration's benefit.

## Tests

`libs/core/kiln_ai/cli/commands/test_migrate_eval_runs.py` — new, over a fixture project
built on `tmp_path` holding a V1 config with an inline record, and a V2 config with one
of each record shape (inline scored, already-pointer, calibration, pre-generation skip,
EvalInput-sourced inline).

**The whole-project guarantee (architecture §9.6)**

- Only V2 inline records change: snapshot every `.kiln` file's bytes before and after, and
  assert the changed set is exactly the expected records plus the new trace files. This is
  the test that catches a migration that reaches too far — the V1 record, the
  already-pointer record and the eval/config files must all be byte-identical.
- Idempotent: a second run plans nothing but `nothing_to_do`, and no file changes.
- `--dry-run` writes nothing: same byte snapshot, and the plan still reports the same
  counts the real run then performs.

**Per-record shape**

- An inline record becomes a pointer record: `scored_run_id` set to the new trace,
  all five inline fields None, and `dataset_id`/`eval_input_id`/`task_run_config_id`/
  `scores`/`reference_data`/`intermediate_outputs` unchanged.
- The rewrite changes *only* those six fields: migrate a record with every field
  populated and diff its dump before and after. The record is rebuilt from its own dump,
  so a field that failed to round-trip would be silently dropped from a file the user
  already has — a claim only as strong as the fields the record carries.
- The synthesized trace carries `input`/`output` from the record, `eval_source` equal to
  the record's `ItemKey` (both source types), and `output.source.run_config_id` equal to
  `task_run_config_id`.
- `task_run_trace` and `task_run_usage`, when present, land as `TaskRun.trace` and
  `TaskRun.usage` — the fields the Phase 4 rollup and a `full_trace` eval read.
- Calibration: `scored_run_id == dataset_id`, no TaskRun created. Including a calibration
  record that was *skipped*, which must get the same treatment (Phase 3's rule).
- A pre-generation skip keeps `skipped_reason`, loses `input`, and gets no
  `scored_run_id`.
- A skipped-at-scoring record (skip reason, `output` None, `input` set) is treated as a
  skip, not as a trace — there is nothing to reconstruct.
- An `mcp` run config produces a `tool_call` trace source with no model properties, the
  other half of `_trace_data_source`.

**Retrying an interrupted migration**

- An apply whose record saves all fail leaves the traces behind; the retry **reuses** them
  (`reuse_trace`, writing no trace) and ends with the same trace ids it started with. The
  claim is that a flaky or Ctrl-C'd migration cannot accumulate undeletable duplicates.
- A trace at the same key holding a *different* generation is **not** reused — the guard
  against a score pointing at output its judge never saw.
- Nor is one **rewritten between plan and apply**: same id and a different output, with
  and without a preserved mtime, *and* same content under a different id — the two halves
  of that check, each of which passes the whole suite when the other one is doing the
  work. Reuse's write-time check has to be reuse's plan-time check, or the content
  guarantee lasts only until the operator answers the prompt.
- All three assert the message, which is the half that went uncovered: a reuse refused on
  content must not be reported as a missing file.

**The point of the whole project**

- After migrating, ask `TraceIndex.get_or_create` for the trace key of each item the way
  the runner asks it, with a generator that fails the test if called: the migrated trace
  comes back and nothing is regenerated. Asserted through the index's own interface rather
  than its stored paths, so it keeps holding when the index changes how it remembers.
- Migrated traces are excluded from `task.runs()` and visible with
  `include_eval_generated=True`.

**Refusals, reported not crashed**

- **A calibration record whose golden item was deleted keeps its own input and output** —
  the one path where migrating could destroy the last copy of what was scored.
- The same for a skip whose dataset item or EvalInput was deleted, both source types.
- **The same when the item is lost *after* the plan is built** — the write-time re-check,
  and the reason the plan-time one is not enough. Parameterized over the three ways an
  item stops being readable: deleted, present but unparseable (a newer Kiln's file), and
  present but holding a different id (a sync replacing it). The last two are what an
  existence check would let through. The `create_trace` record naming the same lost item
  still migrates, so the guard is targeted rather than a blanket refusal.
- **The same when the replacement preserves the file's mtime**, which is what every
  file-syncing tool does. This one has to force `ModelCache` on (it is disabled wherever
  the filesystem reports coarse timestamps, which is the case in CI but not on the
  platforms Kiln ships to) and assert the cache really would have served the plan's parse
  — otherwise it passes without testing anything.
- The refusal report prints the whole path and the whole reason, over a task named
  `Sentiment [v2]` and a pydantic message ending in `[type=value_error, ...]` — the two
  bracket runs rich would otherwise swallow.
- A record whose `task_run_config_id` no longer resolves is left untouched and reported.
- A calibration record with no `dataset_id` is left untouched and reported.
- A record whose `input` no longer matches the task's input schema is left untouched and
  reported (the TaskRun validators reject it at plan time, before any write).
- A file that cannot be parsed at all is reported as a load error and every other record
  still migrates — parameterized over all seven kinds of file the walk opens (task, run
  config, task run, eval input, eval, eval config, eval record), since `_children` is what
  makes each of them survivable.
- A save failure mid-apply is reported and the remaining changes still apply.
- A record written by something else between plan and apply is reported and the other
  writer's version survives — both a concurrent migration and an ordinary edit, which is
  the difference between comparing `scored_run_id` and comparing the record.

**CLI**

- `--dry-run` prints the plan and writes nothing; the confirmation prompt aborts on "n"
  and names both writes; `--yes` skips it; exit code is 1 when something was left
  unmigrated — on a dry run and a declined prompt as much as a real run.
