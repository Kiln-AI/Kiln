from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.task_run import TaskRun


T = TypeVar("T", bound="ChatSnapshot")


@_attrs_define
class ChatSnapshot:
    """JSON-serializable wrapper we store. We retrieve it later and use it as state to resume the chat from.

    Attributes:
        id (str):
        task_run (TaskRun): Represents a single execution of a Task.

            Contains the input used, its source, the output produced, and optional
            repair information if the output needed correction.
    """

    id: str
    task_run: TaskRun
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        task_run = self.task_run.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "task_run": task_run,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.task_run import TaskRun

        d = dict(src_dict)
        id = d.pop("id")

        task_run = TaskRun.from_dict(d.pop("task_run"))

        chat_snapshot = cls(
            id=id,
            task_run=task_run,
        )

        chat_snapshot.additional_properties = d
        return chat_snapshot

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
