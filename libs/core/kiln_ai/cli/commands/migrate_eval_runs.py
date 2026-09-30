"""One-shot migration of V2 eval records from inline traces to trace pointers.

Before the trace/score split an `EvalRun` carried both the scores and a copy of what was
scored. Now the trace is a `TaskRun` and the `EvalRun` names it with `scored_run_id`
(functional spec §2). New records are written that way from the moment the runner
changed; this command converts the ones already on disk, so a project's existing
generations are reusable by the next judge instead of being regenerated (functional
spec §8, architecture §7).

Only V2 records move. V1 records keep their trace inline, forever, and are never rewritten
(functional spec §7).

The command plans the whole project in memory first, constructing every `TaskRun` and
every rewritten `EvalRun` through its normal validators, and only then saves. `--dry-run`
is that first pass alone — not a separate prediction of what a real run would do, but the
real run with the saves withheld.
"""

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Annotated, Any, Dict, List, Type, TypeVar

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from kiln_ai.adapters.eval.trace_index import TraceKey, trace_key
from kiln_ai.cli.commands.package_project import load_project
from kiln_ai.datamodel import Project, Task
from kiln_ai.datamodel.basemodel import (
    ChildLoadError,
    KilnBaseModel,
    KilnParentedModel,
)
from kiln_ai.datamodel.eval import (
    LEGACY_TRACE_FIELDS,
    Eval,
    EvalConfig,
    EvalConfigType,
    EvalInput,
    EvalRun,
)
from kiln_ai.datamodel.eval_splits import ItemKey, eval_run_item_key
from kiln_ai.datamodel.model_cache import ModelCache
from kiln_ai.datamodel.run_config import (
    KilnAgentRunConfigProperties,
    McpRunConfigProperties,
)
from kiln_ai.datamodel.task import TaskRunConfig
from kiln_ai.datamodel.task_output import DataSource, DataSourceType, TaskOutput
from kiln_ai.datamodel.task_run import (
    EvalItemSource,
    MessageUsage,
    TaskRun,
    eval_item_key,
)
from kiln_ai.utils.exhaustive_error import raise_exhaustive_enum_error
from kiln_ai.utils.open_ai_types import ChatCompletionMessageParam

console = Console()

ChildModel = TypeVar("ChildModel", bound=KilnParentedModel)

MIGRATION_ADAPTER_NAME = "kiln_eval_run_migration"
"""What `adapter_name` says on a synthesized trace.

A `synthetic` data source requires one, and the record being migrated does not say which
adapter produced it — only which run config. Naming the migration is honest; guessing an
adapter would put a plausible-looking falsehood on every migrated trace. Other
non-adapter writers label themselves the same way (`kiln_data_gen`,
`kiln_qna_manual_save`)."""


class MigrationAction(str, Enum):
    """What the migration will do with one `EvalRun`."""

    create_trace = "create_trace"
    """Inline scored record: synthesize the TaskRun it describes, then point at it."""

    reuse_trace = "reuse_trace"
    """The trace this record describes is already on disk: point at it, write nothing."""

    link_calibration = "link_calibration"
    """Calibration record: point at the golden dataset item, which is already the trace."""

    clear_inline = "clear_inline"
    """Skipped before generation: drop the inline fields, point at nothing."""

    nothing_to_do = "nothing_to_do"
    """Already pointer-mode, or already in its final shape. What makes this idempotent."""

    unmigratable = "unmigratable"
    """Cannot be migrated safely. Reported, and left exactly as it is on disk."""


ACTION_LABELS: Dict[MigrationAction, str] = {
    # A plan, printed before anything is written — in both modes, so the labels say what
    # will happen rather than what did.
    MigrationAction.create_trace: "Traces to create",
    MigrationAction.reuse_trace: "Existing traces to reuse",
    MigrationAction.link_calibration: "Calibration records to link",
    MigrationAction.clear_inline: "Skipped records to clear",
    MigrationAction.nothing_to_do: "Already migrated (nothing to do)",
    MigrationAction.unmigratable: "Can't be migrated",
}


RECORD_IDENTITY_FIELDS = {"id", "created_at", "created_by", "path"}
"""What two copies of one generation are allowed to differ in: which record they are, not
what they hold. Named on the nested models too — a `TaskOutput` is a record in its own
right, with its own id and timestamp, so a top-level exclude would compare two identical
generations as different."""

TRACE_IDENTITY_EXCLUDES: Any = {
    **{name: True for name in RECORD_IDENTITY_FIELDS},
    "output": RECORD_IDENTITY_FIELDS,
    "repaired_output": RECORD_IDENTITY_FIELDS,
}


def _same_generation(existing: TaskRun, planned: TaskRun) -> bool:
    return existing.model_dump(exclude=TRACE_IDENTITY_EXCLUDES) == planned.model_dump(
        exclude=TRACE_IDENTITY_EXCLUDES
    )


@dataclass(frozen=True)
class ItemReference:
    """A record a change defers to, and what the plan knew about it.

    A change that clears the record's own copy of what was scored is only safe while what
    it defers to is still there, so that precondition is re-checked immediately before the
    write and not just when the plan was made — the confirmation prompt sits in between,
    and nothing stops the app deleting a dataset item, or a sync replacing one, while it is
    up.

    Re-checked by reading *this* path, not by looking the id up again.
    `from_id_and_parent_path` rescans the whole store per call, and with a cold model
    cache that means re-reading every run in the dataset, once per record. The path is
    exact for what this needs: `save_to_file` keeps a record at the path it was loaded
    from, and `delete()` removes the directory it lives in. A moved file reads as missing,
    which refuses the change — the safe direction.
    """

    key: ItemKey
    path: Path

    expected: TaskRun | None = None
    """The trace the plan matched, when it matched on more than the id.

    A dataset item is chosen by id, so an id is all the write-time check can re-ask. A
    *reused trace* is chosen by its content — `existing_trace` refuses one whose output
    differs, because a score must not end up pointing at output its judge never saw — and
    a check that re-asked only the id would give exactly that guarantee up, at the one
    moment it can still refuse while the record's own copy is still on disk."""

    @property
    def still_readable(self) -> bool:
        """Whether it is still at this path, still loads, and is still what was planned.

        The same question asked at plan time, asked the same way. An existence check would
        be weaker than its own counterpart: a file written by a newer Kiln (which
        `_children` treats as normal) or one replaced by a sync carrying a different id is
        present but is not the item, and clearing the record's last copy in favour of it
        would destroy that copy silently. The same reasoning is why a reused trace is
        re-compared, not just re-identified.

        The cache is dropped for this path first, and that is the point of the re-read
        rather than an optimization detail. `ModelCache` validates on mtime alone, and the
        plan's own `readonly=True` scan is what put this item in it — so a replacement
        that preserves mtime (`rsync -t`, Syncthing, Dropbox, iCloud all do, by design)
        would be served the plan's parse and pass a check whose entire job is to notice
        that the plan is stale. Reading one small file at a known path is cheap; reading
        the answer we are trying to invalidate is not cheap at all.
        """
        source_type, item_id = self.key
        ModelCache.shared().invalidate(self.path)
        try:
            loaded: TaskRun | EvalInput = (
                TaskRun.load_from_file(self.path, readonly=True)
                if source_type == "task_run"
                else EvalInput.load_from_file(self.path, readonly=True)
            )
        except Exception:
            return False

        if loaded.id != item_id:
            return False
        if self.expected is None:
            return True
        # `_same_generation` ignores a record's own identity fields, so the id check above
        # is not redundant with it: it is what keeps `scored_run_id` resolving.
        return isinstance(loaded, TaskRun) and _same_generation(loaded, self.expected)


@dataclass(frozen=True)
class PlannedChange:
    """One record's migration, fully built but not yet saved.

    `trace` and `migrated` are the exact objects `apply_plan` will write, constructed
    through their own validators during planning. So a record that would produce an
    invalid file is found by a dry run, not by a half-finished write.
    """

    action: MigrationAction
    eval_run: EvalRun
    detail: str = ""
    trace: TaskRun | None = None
    migrated: EvalRun | None = None
    requires_item: ItemReference | None = None
    """The dataset item this change hands the record's content over to, if any."""


@dataclass
class MigrationPlan:
    changes: List[PlannedChange] = field(default_factory=list)
    v1_configs_skipped: int = 0
    """V1 eval configs left alone. Their records are never loaded, let alone rewritten."""

    load_errors: List[ChildLoadError] = field(default_factory=list)
    """Files that could not be read at all — typically written by a newer Kiln and synced
    here. Reported and stepped over: one unreadable file must not stop a whole project
    from migrating."""

    def by_action(self, action: MigrationAction) -> List[PlannedChange]:
        return [change for change in self.changes if change.action == action]

    @property
    def pending_writes(self) -> List[PlannedChange]:
        """The changes that will touch disk."""
        return [change for change in self.changes if change.migrated is not None]

    @property
    def traces_to_create(self) -> int:
        return sum(1 for change in self.changes if change.trace is not None)


@dataclass(frozen=True)
class MigrationFailure:
    """A change that was planned but could not be saved."""

    eval_run: EvalRun
    message: str


class UnmigratableRecord(Exception):
    """A record the migration refuses to rewrite, with the reason to report."""


def _children(
    child_class: Type[ChildModel],
    parent: KilnBaseModel,
    plan: MigrationPlan,
    readonly: bool = False,
) -> List[ChildModel]:
    """Every child that loads, with the ones that don't recorded on the plan.

    Project folders sync between clients on different Kiln versions, so a single file
    written by a newer build is unreadable here while its siblings are fine. The read side
    already treats that as normal (`EvalsResponse.load_error_count`); a one-shot
    whole-project command has more reason to, not less.
    """
    children, errors = child_class.all_children_of_parent_path_with_errors(
        parent.path, readonly=readonly
    )
    plan.load_errors.extend(errors)
    return children


@dataclass(frozen=True)
class TaskIndex:
    """What a task already has on disk that the migration has to know about.

    Two questions, one scan of the task's stores, once per task rather than once per
    record:

    - **Where each dataset item is** (`items`). Consulted before clearing a record's
      inline copy of what it scored: `dataset_id` and `eval_input_id` are ids, not
      references, and nothing guarantees they still resolve — delete protection covers
      eval *traces* (architecture §6), not the golden items and dataset rows an eval
      record names. Clearing the record's own copy in favour of something that no longer
      exists would destroy the last readable version of it.
    - **Which eval traces already exist** (`trace_paths`), keyed the way the runner's
      `TraceIndex` keys them. A record whose trace is already on disk points at it instead
      of minting a second copy.
    """

    items: Dict[ItemKey, Path]
    trace_paths: Dict[TraceKey, List[Path]]

    @classmethod
    def load(cls, task: Task, plan: MigrationPlan) -> "TaskIndex":
        items: Dict[ItemKey, Path] = {}
        traces: Dict[TraceKey, List[Path]] = {}

        for run in _children(TaskRun, task, plan, readonly=True):
            if not run.id or not run.path:
                continue
            items[("task_run", run.id)] = run.path
            run_config_id = (
                run.output.source.run_config_id if run.output.source else None
            )
            if run.eval_source is not None and run_config_id:
                key = trace_key(eval_item_key(run.eval_source), run_config_id)
                traces.setdefault(key, []).append(run.path)

        for eval_input in _children(EvalInput, task, plan, readonly=True):
            if eval_input.id and eval_input.path:
                items[("eval_input", eval_input.id)] = eval_input.path

        return cls(items=items, trace_paths=traces)

    def reference(self, item: ItemKey) -> ItemReference | None:
        path = self.items.get(item)
        return None if path is None else ItemReference(key=item, path=path)

    def existing_trace(self, planned: TaskRun) -> TaskRun | None:
        """A trace already on disk that is this generation, or None.

        Identity is the whole record, not the key: a trace at the same key with a
        *different* output is a different generation, and pointing a score at it would say
        the judge saw something it never saw. Content-identical means the score means
        exactly what it meant before, so reuse is invisible — which is what makes an
        interrupted migration idempotent instead of leaving a fresh undeletable duplicate
        behind on every retry.

        Functional spec §8 punts deduplication, and this is not it: two records only ever
        share a trace here when what they scored was byte-identical anyway.
        """
        if planned.eval_source is None or planned.output.source is None:
            return None
        run_config_id = planned.output.source.run_config_id
        if not run_config_id:
            return None
        key = trace_key(eval_item_key(planned.eval_source), run_config_id)

        for path in self.trace_paths.get(key, []):
            try:
                existing = TaskRun.load_from_file(path)
            except Exception:
                continue
            if _same_generation(existing, planned):
                return existing
        return None


def _trace_data_source(run_config: TaskRunConfig) -> DataSource:
    """Where a synthesized trace says it came from.

    Mirrors `BaseAdapter._properties_for_task_output`, so a migrated trace describes its
    generation the way a live one does. `run_config_id` is the load-bearing field: with
    the item's `eval_source`, it is the key the trace index reuses a trace by
    (functional spec §2.1), so a trace missing it would be regenerated on every future
    eval.
    """
    properties = run_config.run_config_properties
    match properties:
        case McpRunConfigProperties():
            return DataSource(
                type=DataSourceType.tool_call,
                run_config_id=run_config.id,
                run_config=properties,
            )
        case KilnAgentRunConfigProperties():
            return DataSource(
                type=DataSourceType.synthetic,
                properties={
                    "adapter_name": MIGRATION_ADAPTER_NAME,
                    "model_name": properties.model_name,
                    "model_provider": properties.model_provider_name,
                    "prompt_id": properties.prompt_id,
                    "structured_output_mode": properties.structured_output_mode,
                    "temperature": properties.temperature,
                    "top_p": properties.top_p,
                },
                run_config_id=run_config.id,
                run_config=properties,
            )
        case _:
            raise_exhaustive_enum_error(properties)


def _parsed_trace(eval_run: EvalRun) -> list[ChatCompletionMessageParam] | None:
    """The record's inline trace, back as the message list it was serialized from.

    The V1 runner wrote this field with `json.dumps`. A V2 record never had one written
    (only the V1 path ever set it), so this is here for completeness rather than for data
    anyone is expected to have — which is also why an unreadable one refuses the record
    instead of quietly dropping it: a trace is not something to lose silently.
    """
    if eval_run.task_run_trace is None:
        return None
    try:
        parsed = json.loads(eval_run.task_run_trace)
    except json.JSONDecodeError as e:
        raise UnmigratableRecord(f"task_run_trace is not valid JSON: {e}") from e
    if not isinstance(parsed, list):
        raise UnmigratableRecord(
            f"task_run_trace is a JSON {type(parsed).__name__}, not a list of messages."
        )
    return parsed


def _synthesized_trace(
    task: Task, eval_run: EvalRun, run_config: TaskRunConfig
) -> TaskRun:
    """The TaskRun an inline record describes.

    One per record, with no grouping: several eval configs may hold records of the same
    generation, and merging them would need a dedupe key the records don't carry.
    Functional spec §8 punts that deliberately — the duplication is small, and from here
    on the live trace lookup produces one trace per key anyway.
    """
    if eval_run.input is None or eval_run.output is None:
        raise UnmigratableRecord(
            "A scored record needs both input and output to reconstruct the run it scored "
            f"(input {'set' if eval_run.input is not None else 'missing'}, "
            f"output {'set' if eval_run.output is not None else 'missing'})."
        )

    source_type, source_id = eval_run_item_key(eval_run)
    if not source_id:
        raise UnmigratableRecord("The record does not name the dataset item it scored.")

    trace = _parsed_trace(eval_run)
    data_source = _trace_data_source(run_config)

    return TaskRun(
        parent=task,
        input=eval_run.input,
        # Architecture §7: the synthesized run names the run config it was produced by, on
        # both sources. A live trace records the input as human-authored (the adapter's
        # default), which a migration cannot honestly copy — the record it is rebuilt from
        # names no author, and attributing it to whoever is running the migration would be
        # worse than naming the run that produced it.
        input_source=data_source,
        output=TaskOutput(output=eval_run.output, source=data_source),
        trace=trace,
        usage=eval_run.task_run_usage,
        cumulative_usage=MessageUsage.from_trace(trace),
        eval_source=EvalItemSource(source_type=source_type, source_id=source_id),
    )


def _pointer_record(
    eval_run: EvalRun, eval_config: EvalConfig, scored_run_id: str | None
) -> EvalRun:
    """The record rewritten to point at its trace instead of carrying one.

    Built as a new instance rather than by assignment. `validate_assignment` validates
    every intermediate state, and the two halves of this change have no legal order
    between them: clearing `input` first fails "a legacy EvalRun requires input", and
    setting `scored_run_id` first fails "must not carry inline trace data". Constructing
    the end state validates it once, whole, before anything reaches disk.

    The parent is passed in rather than read off `eval_run.parent`, which would reload the
    EvalConfig from disk once per record — children are loaded without one, and resolve it
    lazily from their path.
    """
    fields = eval_run.model_dump()
    fields.update({name: None for name in LEGACY_TRACE_FIELDS})
    fields["input"] = None
    fields["scored_run_id"] = scored_run_id
    fields["parent"] = eval_config
    fields["path"] = eval_run.path
    return EvalRun.model_validate(fields)


def _carries_inline_data(eval_run: EvalRun) -> bool:
    return eval_run.input is not None or any(
        getattr(eval_run, name) is not None for name in LEGACY_TRACE_FIELDS
    )


def _required_item(eval_run: EvalRun, index: TaskIndex) -> ItemReference:
    """The dataset item a record may hand its content over to, or a refusal.

    Clearing a record's inline copy is only safe while what it names is still readable:
    the item supplies the golden output a calibration record scored, and the input a
    skipped record displays (Phase 4's fallback). With the item gone, the record's own
    copy is the last one there is.
    """
    key = eval_run_item_key(eval_run)
    reference = index.reference(key)
    if reference is None:
        source, item_id = key
        raise UnmigratableRecord(
            f"The {'dataset item' if source == 'task_run' else 'eval input'} '{item_id}' this "
            "record names no longer exists, so clearing the record's own copy of what it "
            "scored would leave nothing to read."
        )
    return reference


def plan_eval_run(
    task: Task,
    eval_config: EvalConfig,
    eval_run: EvalRun,
    run_configs: Dict[str, TaskRunConfig],
    index: TaskIndex,
) -> PlannedChange:
    """What the migration will do with one record, and everything it needs to do it.

    Branch order follows architecture §7, and calibration is checked above the skip branch
    on purpose: a calibration record points at the golden item whether or not the judge was
    reached. That is the rule Phase 3 settled for live skips, so an old calibration skip
    must migrate to the same shape a new one is written in.

    Every branch that clears inline data the record is the last copy of records what it is
    deferring to in `requires_item`, so the write pass can re-check that it is still there:
    the two clearing branches ask `_required_item` — by the same `eval_run_item_key` the
    runner and the index use, so "these check the same thing" is visible rather than
    something the reader has to prove — and the reuse branch names the trace it found.
    Only `create_trace` needs no check, because it writes the replacement itself.
    """
    if eval_run.scored_run_id is not None:
        return PlannedChange(
            MigrationAction.nothing_to_do, eval_run, "already points at a trace"
        )

    try:
        if eval_run.eval_config_eval:
            if eval_run.dataset_id is None:
                raise UnmigratableRecord(
                    "A calibration record scores a dataset item, but this one has no dataset_id."
                )
            # dataset_id is set, so the key is ("task_run", dataset_id): the golden item.
            golden = _required_item(eval_run, index)
            return PlannedChange(
                MigrationAction.link_calibration,
                eval_run,
                migrated=_pointer_record(eval_run, eval_config, eval_run.dataset_id),
                requires_item=golden,
            )

        if eval_run.skipped_reason is not None and eval_run.output is None:
            # Skipped with no output kept: either it was skipped before anything was
            # generated, or it was skipped at scoring time, which also wrote no output
            # (functional spec §4.6). Either way there is no trace here to reconstruct.
            if not _carries_inline_data(eval_run):
                return PlannedChange(
                    MigrationAction.nothing_to_do, eval_run, "skipped, nothing inline"
                )
            return PlannedChange(
                MigrationAction.clear_inline,
                eval_run,
                requires_item=_required_item(eval_run, index),
                migrated=_pointer_record(eval_run, eval_config, None),
            )

        run_config = (
            run_configs.get(eval_run.task_run_config_id)
            if eval_run.task_run_config_id
            else None
        )
        if run_config is None:
            raise UnmigratableRecord(
                f"Run config '{eval_run.task_run_config_id}' no longer exists, so the trace "
                "can't say which model produced it."
            )

        trace = _synthesized_trace(task, eval_run, run_config)
        existing = index.existing_trace(trace)
        if existing is not None:
            # An earlier run of this migration wrote this exact trace and was interrupted
            # before the record could point at it. Minting a second one would leave the
            # first orphaned — and since Phase 4, an eval-generated run can't be deleted
            # from the app, so every retry would add a permanent duplicate.
            return PlannedChange(
                MigrationAction.reuse_trace,
                eval_run,
                detail="the trace this record describes is already on disk",
                migrated=_pointer_record(eval_run, eval_config, existing.id),
                requires_item=ItemReference(
                    key=("task_run", existing.id),
                    path=existing.path,
                    # Matched on content, so re-checked on content: this is the copy the
                    # write pass compares what is on disk against.
                    expected=existing,
                )
                if existing.id and existing.path
                else None,
            )
        return PlannedChange(
            MigrationAction.create_trace,
            eval_run,
            trace=trace,
            migrated=_pointer_record(eval_run, eval_config, trace.id),
        )
    except UnmigratableRecord as e:
        return PlannedChange(MigrationAction.unmigratable, eval_run, str(e))
    except Exception as e:
        # Anything a validator refuses — an input that no longer matches the task's
        # schema, scores that don't match the eval — is a record left alone and reported,
        # not a migration that stops halfway through a project.
        return PlannedChange(
            MigrationAction.unmigratable, eval_run, f"{type(e).__name__}: {e}"
        )


def _v2_configs(task: Task, plan: MigrationPlan) -> List[EvalConfig]:
    """The task's V2 eval configs, counting the V1 ones it steps over.

    V1 records keep their trace inline forever (functional spec §7), so their configs are
    identified and then left unopened — nothing here has any business reading them.
    """
    configs: List[EvalConfig] = []
    for eval in _children(Eval, task, plan):
        for eval_config in _children(EvalConfig, eval, plan):
            if eval_config.config_type != EvalConfigType.v2:
                plan.v1_configs_skipped += 1
                continue
            configs.append(eval_config)
    return configs


def plan_project(project: Project) -> MigrationPlan:
    """Everything the migration would write, without writing any of it."""
    plan = MigrationPlan()

    for task in _children(Task, project, plan):
        v2_configs = _v2_configs(task, plan)
        if not v2_configs:
            # Nothing to migrate here, so the task's dataset is never scanned.
            continue

        run_configs = {
            rc.id: rc for rc in _children(TaskRunConfig, task, plan) if rc.id
        }
        index = TaskIndex.load(task, plan)

        for eval_config in v2_configs:
            for eval_run in _children(EvalRun, eval_config, plan):
                plan.changes.append(
                    plan_eval_run(task, eval_config, eval_run, run_configs, index)
                )

    return plan


def apply_plan(plan: MigrationPlan) -> List[MigrationFailure]:
    """Save what the plan built, trace before score record.

    That order is what an interruption is judged on (architecture §7): a saved trace with
    no record pointing at it is an orphan — harmless, and hidden from every dataset
    surface by default — while the reverse would be a score pointing at a file that was
    never written.

    Both of the plan's preconditions are re-checked here, immediately before each write.
    The plan is a snapshot of the project, and a confirmation prompt sits between the two
    passes, so the app is free to have changed either half in between:

    - the **record** may have been rewritten, which a stale planned object would clobber;
    - the **item** the record is about to defer to may have been deleted or replaced,
      which is the one way this command can destroy data — it clears the record's own copy
      of what was scored, and a plan-time check alone would be minutes stale by the time
      it does.

    Both re-checks are the plan-time check re-run, not a cheaper approximation of it: the
    record is compared whole, and the item is loaded and identified.
    """
    failures: List[MigrationFailure] = []

    for change in plan.changes:
        if change.migrated is None:
            continue
        try:
            stale = _stale_precondition(change)
            if stale is not None:
                failures.append(MigrationFailure(change.eval_run, stale))
                continue
            if change.trace is not None:
                change.trace.save_to_file()
            change.migrated.save_to_file()
        except Exception as e:
            failures.append(
                MigrationFailure(change.eval_run, f"{type(e).__name__}: {e}")
            )

    return failures


def _stale_precondition(change: PlannedChange) -> str | None:
    """Why this change can no longer be written, re-read from disk. None if it still can.

    The record is compared whole rather than on `scored_run_id` alone: anything else the
    app wrote — an added rating, an edited score — would otherwise be silently reverted by
    a planned object built before it. Two dumps of an unmodified record are exactly equal,
    so there is nothing to be lax about.
    """
    if change.eval_run.path is None:
        raise ValueError("Only records loaded from disk can be migrated")

    if EvalRun.load_from_file(change.eval_run.path).model_dump() != (
        change.eval_run.model_dump()
    ):
        return (
            "Changed on disk after the plan was built. Left alone; re-run to migrate it "
            "from its current state."
        )

    if change.requires_item is not None and not change.requires_item.still_readable:
        return _stale_reference_message(change.requires_item)

    return None


def _stale_reference_message(reference: ItemReference) -> str:
    """Why what this change was going to defer to can no longer be deferred to.

    Two references, two failures, two messages. A reuse refused on content is *not* a
    missing file — it is present and parses fine — and telling an operator to go looking
    for one would send them after a file sitting exactly where the message names it.
    """
    _, item_id = reference.key
    if reference.expected is not None:
        return (
            f"The trace '{item_id}' this record was going to point at is not the one the "
            "plan matched — it has been changed, replaced or removed since. Pointing the "
            "score at it would attribute it to a generation the judge never saw."
        )
    return (
        f"The item '{item_id}' this record was going to defer to is gone or no longer "
        "readable since the plan was built, so clearing the record's own copy would "
        "leave nothing to read."
    )


def _reported_file(path: Path | None, reason: str) -> str:
    """One file the command is leaving alone, and why — printed verbatim.

    Both halves are escaped because both routinely contain square brackets, and rich would
    read those as markup and swallow them: task names allow brackets (`Sentiment [v2]`, in
    the directory name and so in every path under it), and every pydantic ValidationError
    ends `[type=..., input_value=..., input_type=...]`. This is the surface that tells an
    operator what a data-safety command refused and where, so a path that no longer
    resolves or a reason that stops mid-sentence is worse than no report at all.
    """
    return f"  [dim]{escape(str(path))}[/dim]\n    {escape(reason)}"


def print_plan(plan: MigrationPlan) -> None:
    table = Table(title="Eval record migration plan")
    table.add_column("Record", style="white")
    table.add_column("Count", style="cyan", justify="right")

    for action in MigrationAction:
        table.add_row(ACTION_LABELS[action], str(len(plan.by_action(action))))
    table.add_row("V1 eval configs (untouched)", str(plan.v1_configs_skipped))

    console.print(table)

    unmigratable = plan.by_action(MigrationAction.unmigratable)
    if unmigratable:
        console.print(
            f"\n[yellow]Warning:[/yellow] {len(unmigratable)} record(s) can't be migrated. "
            "They are left exactly as they are, and still display."
        )
        for change in unmigratable:
            console.print(_reported_file(change.eval_run.path, change.detail))

    if plan.load_errors:
        console.print(
            f"\n[yellow]Warning:[/yellow] {len(plan.load_errors)} file(s) could not be read, "
            "and were stepped over. They may have been written by a newer version of Kiln."
        )
        for error in plan.load_errors:
            console.print(_reported_file(error.path, error.message))


def migrate_eval_runs(
    project_path: Annotated[
        Path | None,
        typer.Argument(help="Path to project.kiln file or folder containing it"),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Show what would change, and write nothing."),
    ] = False,
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip the confirmation prompt."),
    ] = False,
) -> MigrationPlan:
    """Move V2 eval records onto their task runs.

    Each V2 eval record that still carries a copy of what it scored gets that copy
    written out as a task run, and keeps only a pointer to it. Judges can then score a
    generation that already exists instead of paying to make another one.

    V1 eval records are not touched. Running this twice is the same as running it once.
    """
    if project_path is None:
        console.print(
            "\n[red]Error:[/red] No project path provided. You must provide this argument.\n"
        )
        raise typer.Exit(1)

    project = load_project(project_path)
    console.print(f"Loaded project: {escape(project.name)}")

    plan = plan_project(project)
    print_plan(plan)

    if dry_run:
        console.print("\n[dim]Dry run: nothing was written.[/dim]")
        _exit_if_incomplete(plan, [])
        return plan

    pending = plan.pending_writes
    failures: List[MigrationFailure] = []

    if not pending:
        console.print("\n[green]Nothing to migrate.[/green]")
    else:
        if not yes and not typer.confirm(f"\n{_write_prompt(plan)}"):
            console.print("\n[dim]Aborted: nothing was written.[/dim]")
            # Same signal a --dry-run of this project gives: what the command found does
            # not depend on whether the operator typed "n" or never got to the prompt.
            _exit_if_incomplete(plan, [])
            raise typer.Exit(0)

        failures = apply_plan(plan)
        if failures:
            console.print(f"\n[red]{len(failures)} record(s) failed to save:[/red]")
            for failure in failures:
                console.print(_reported_file(failure.eval_run.path, failure.message))
        else:
            console.print(
                f"\n[bold green]Done![/bold green] Migrated {len(pending)} eval record(s)."
            )

    _exit_if_incomplete(plan, failures)
    return plan


def _write_prompt(plan: MigrationPlan) -> str:
    """The last thing a user sees before a one-way rewrite, so it names both writes."""
    prompt = f"Update {len(plan.pending_writes)} eval record(s)"
    if plan.traces_to_create:
        prompt += f" and create {plan.traces_to_create} task run(s)"
    return prompt + "?"


def _exit_if_incomplete(plan: MigrationPlan, failures: List[MigrationFailure]) -> None:
    """Exit non-zero when the project is only partly migrated.

    Applies to a dry run too: a preflight is the more likely thing to script, so it has
    more reason to signal than the run that follows it.

    Records and files are counted apart. They are different things — an unreadable
    dataset file is not an eval record that failed to migrate, and one unreadable golden
    item also makes every calibration record naming it unmigratable, so a single total
    would both mislabel and double-count.
    """
    records = len(plan.by_action(MigrationAction.unmigratable)) + len(failures)
    files = len(plan.load_errors)
    if not records and not files:
        return

    reasons = []
    if records:
        reasons.append(f"{records} eval record(s) were not migrated")
    if files:
        reasons.append(f"{files} file(s) could not be read")
    console.print(f"\n[yellow]{', and '.join(reasons)} — see above.[/yellow]")
    raise typer.Exit(1)
