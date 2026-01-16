from __future__ import annotations

from collections.abc import Mapping
from io import BytesIO
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from .. import types
from ..models.body_start_gepa_job_v1_jobs_gepa_job_start_post_token_budget import (
    BodyStartGepaJobV1JobsGepaJobStartPostTokenBudget,
)
from ..types import File

T = TypeVar("T", bound="BodyStartGepaJobV1JobsGepaJobStartPost")


@_attrs_define
class BodyStartGepaJobV1JobsGepaJobStartPost:
    """
    Attributes:
        token_budget (BodyStartGepaJobV1JobsGepaJobStartPostTokenBudget): The token budget to use
        task_id (str): The task ID
        target_run_config_id (str): The target run config ID
        project_zip (File): The project zip file
    """

    token_budget: BodyStartGepaJobV1JobsGepaJobStartPostTokenBudget
    task_id: str
    target_run_config_id: str
    project_zip: File
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        token_budget = self.token_budget.value

        task_id = self.task_id

        target_run_config_id = self.target_run_config_id

        project_zip = self.project_zip.to_tuple()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "token_budget": token_budget,
                "task_id": task_id,
                "target_run_config_id": target_run_config_id,
                "project_zip": project_zip,
            }
        )

        return field_dict

    def to_multipart(self) -> types.RequestFiles:
        files: types.RequestFiles = []

        files.append(("token_budget", (None, str(self.token_budget.value).encode(), "text/plain")))

        files.append(("task_id", (None, str(self.task_id).encode(), "text/plain")))

        files.append(("target_run_config_id", (None, str(self.target_run_config_id).encode(), "text/plain")))

        files.append(("project_zip", self.project_zip.to_tuple()))

        for prop_name, prop in self.additional_properties.items():
            files.append((prop_name, (None, str(prop).encode(), "text/plain")))

        return files

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        token_budget = BodyStartGepaJobV1JobsGepaJobStartPostTokenBudget(d.pop("token_budget"))

        task_id = d.pop("task_id")

        target_run_config_id = d.pop("target_run_config_id")

        project_zip = File(payload=BytesIO(d.pop("project_zip")))

        body_start_gepa_job_v1_jobs_gepa_job_start_post = cls(
            token_budget=token_budget,
            task_id=task_id,
            target_run_config_id=target_run_config_id,
            project_zip=project_zip,
        )

        body_start_gepa_job_v1_jobs_gepa_job_start_post.additional_properties = d
        return body_start_gepa_job_v1_jobs_gepa_job_start_post

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
