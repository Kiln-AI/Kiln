"""Resolving an eval's splits to their items, from whichever store backs them.

This is the one seam that knows a split can be backed by either `TaskRun`s or
`EvalInput`s: callers ask for a split by name and get a `ResolvedSplit`. That is now an
invariant rather than a destination — `eval_runner.py`, the eval job worker, and every
split read in `eval_api.py` resolve here, so nothing outside this module decides which
store an eval's items come from (architecture 3.4).

The one deliberate exception is the **golden set** (`eval_configs_filter_id`), which
`eval_api` (`runs_in_filter`, and `get_eval_configs_score_summary` inline) and
`EvalRunner.collect_tasks_for_eval_config_eval` still resolve directly with
`dataset_filter_from_id`. Golden is TaskRun-only by definition, and
routing it through here would imply it could be EvalInput-backed, which is precisely what
this project says it cannot be.
"""

from dataclasses import dataclass, field
from typing import List, Literal, Set, Tuple

from kiln_ai.datamodel.basemodel import ID_TYPE
from kiln_ai.datamodel.dataset_filters import (
    dataset_filter_from_id,
    eval_input_filter_from_id,
)
from kiln_ai.datamodel.eval import (
    Eval,
    EvalInput,
    EvalInputSplit,
    EvalRun,
    EvalSplitName,
    TaskRunSplit,
)
from kiln_ai.datamodel.task import Task
from kiln_ai.datamodel.task_run import TaskRun
from kiln_ai.utils.exhaustive_error import raise_exhaustive_enum_error

ItemSource = Literal["task_run", "eval_input"]
"""Which store an item came from."""

ItemKey = Tuple[ItemSource, ID_TYPE]
"""Identity of a dataset item. Never a bare id: ids are drawn from one 12-digit
generator shared by every model type, so a TaskRun and an EvalInput can collide."""


def _item_type_for_source(source: ItemSource) -> type:
    """The model type a split declaring this source must hold.

    A match rather than a dict so a new ItemSource that nothing here knows how to check is
    a type error at authoring time and a ValueError at runtime, not a source that quietly
    validates against nothing.
    """
    match source:
        case "task_run":
            return TaskRun
        case "eval_input":
            return EvalInput
        case _:
            raise_exhaustive_enum_error(source)


@dataclass(frozen=True)
class ResolvedSplit:
    """The items in one of an eval's splits, from a single store."""

    name: str
    source: ItemSource
    items: List[TaskRun] | List[EvalInput]
    """The split's items, all from the store `source` names. `__post_init__` checks that
    against the first item only, not every item: the annotation is a list of one type, so
    "do the items match the declared source" is one bit that any item answers, and every
    producer fills the list from a single store's iterator. A split can hold every run in
    a dataset, and an O(n) isinstance sweep would re-derive per item what the annotation
    already claims for the list. The cost is that a hand-built list mixing both types is
    caught only if its first item is the wrong one — a shape the annotation already
    forbids, and a narrower hole than the unchecked source this replaces."""
    eval_id: ID_TYPE
    """The eval this was resolved from. Carried so a consumer handed a split can check it
    belongs to the eval it is working on: once a split is a value passed between layers,
    nothing else ties the items to the eval whose judges are about to score them."""
    _item_keys: Set[ItemKey] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        expected_type = _item_type_for_source(self.source)
        if self.items and not isinstance(self.items[0], expected_type):
            raise ValueError(
                f"Split '{self.name}' declares source '{self.source}' but holds "
                f"{type(self.items[0]).__name__} items. A split's source is what every "
                "consumer keys its items on, while an EvalRun records the id field the "
                "item's own type picks, so a split whose two disagree writes results "
                "under one identity and looks them up under another."
            )
        object.__setattr__(
            self, "_item_keys", {(self.source, item.id) for item in self.items}
        )

    def item_keys(self) -> Set[ItemKey]:
        return set(self._item_keys)

    def __contains__(self, key: ItemKey) -> bool:
        return key in self._item_keys

    def __len__(self) -> int:
        """How many distinct items the split holds.

        Deliberately the key count, not `len(self.items)`: every consumer that *measures
        progress against* a split builds its numerator by intersecting item keys, so a
        denominator taken from the item list is one its own numerator could never reach —
        a percent_complete stuck below 100, or an is_complete that never fires.

        This is not a global claim about every size derived from a split. Consumers that
        *iterate* the items — `EvalRunner.collect_tasks_for_task_run_eval`, and therefore
        the total `AsyncJobRunner` streams while a job runs — still count items, because
        that is the amount of work they will do. Those two totals differ only if one store
        ever yields two items with the same id, the same precondition that makes this
        choice free.
        """
        return len(self._item_keys)

    def __bool__(self) -> bool:
        """Always True: a resolved split exists, however many items it holds.

        Without this, `__len__` decides truthiness and an empty split is falsy, which
        collapses "this split exists but has no items yet" into "this eval has no such
        split" — the one distinction this module is built to preserve, and the difference
        between telling a user to generate data and telling them to configure a split.
        Absence is `resolve_split` returning None; emptiness is `len(...) == 0`. Every
        caller tests absence with `is None` today, so this defends the next one rather
        than fixing a live bug.
        """
        return True


def resolve_split(task: Task, eval: Eval, split: EvalSplitName) -> ResolvedSplit | None:
    """The items in one of an eval's splits, from whichever store backs it.

    Returns None when the eval has no such split — the caller decides whether that is a
    422, a zero, or a skip. An eval that has the split but whose filter matches nothing
    returns an empty ResolvedSplit, which is a different answer.
    """
    split_ref = eval.splits.get(split)
    match split_ref:
        case None:
            return None
        case TaskRunSplit():
            task_run_filter = dataset_filter_from_id(split_ref.filter_id)
            return ResolvedSplit(
                name=split,
                source="task_run",
                items=[run for run in task.runs(readonly=True) if task_run_filter(run)],
                eval_id=eval.id,
            )
        case EvalInputSplit():
            eval_input_filter = eval_input_filter_from_id(split_ref.filter_id)
            return ResolvedSplit(
                name=split,
                source="eval_input",
                items=[
                    eval_input
                    for eval_input in task.eval_inputs(readonly=True)
                    if eval_input_filter(eval_input)
                ],
                eval_id=eval.id,
            )
        case _:
            raise_exhaustive_enum_error(split_ref)


def eval_run_item_key(eval_run: EvalRun) -> ItemKey:
    """The item this run scored.

    EvalRun validates that exactly one of dataset_id (TaskRun) or eval_input_id
    (EvalInput) is set, so this is total for any validated run.
    """
    if eval_run.dataset_id is not None:
        return ("task_run", eval_run.dataset_id)
    if eval_run.eval_input_id is not None:
        return ("eval_input", eval_run.eval_input_id)
    raise ValueError(
        f"Eval run '{eval_run.id}' has neither a dataset_id nor an eval_input_id, so the item it scored can't be identified."
    )
