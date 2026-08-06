"""Resolving an eval's splits to their items, from whichever store backs them.

This is meant to be the one seam that knows a split can be backed by either `TaskRun`s
or `EvalInput`s: callers ask for a split by name and get a `ResolvedSplit`. That is not
yet true of the codebase — `eval_runner.py` still branches on the source, and the API
layer still resolves filters itself. Migrating those readers here is the rest of this
project (architecture 3.4); until then, read this module as the destination rather than
as an invariant that already holds.
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


@dataclass(frozen=True)
class ResolvedSplit:
    """The items in one of an eval's splits, from a single store."""

    name: str
    source: ItemSource
    items: List[TaskRun] | List[EvalInput]
    _item_keys: Set[ItemKey] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "_item_keys", {(self.source, item.id) for item in self.items}
        )

    def item_keys(self) -> Set[ItemKey]:
        return set(self._item_keys)

    def __contains__(self, key: ItemKey) -> bool:
        return key in self._item_keys

    def __len__(self) -> int:
        return len(self.items)


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
