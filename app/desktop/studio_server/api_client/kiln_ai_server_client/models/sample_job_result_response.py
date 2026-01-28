from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.job_status import JobStatus
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.output_file_info import OutputFileInfo
    from ..models.sample_job_output import SampleJobOutput


T = TypeVar("T", bound="SampleJobResultResponse")


@_attrs_define
class SampleJobResultResponse:
    """Response model for sample job result.

    Attributes:
        status (JobStatus): Job execution status aligned with Google Cloud Run Job execution states.
        output (None | SampleJobOutput | Unset):
        output_files (list[OutputFileInfo] | Unset):
    """

    status: JobStatus
    output: None | SampleJobOutput | Unset = UNSET
    output_files: list[OutputFileInfo] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.sample_job_output import SampleJobOutput

        status = self.status.value

        output: dict[str, Any] | None | Unset
        if isinstance(self.output, Unset):
            output = UNSET
        elif isinstance(self.output, SampleJobOutput):
            output = self.output.to_dict()
        else:
            output = self.output

        output_files: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.output_files, Unset):
            output_files = []
            for output_files_item_data in self.output_files:
                output_files_item = output_files_item_data.to_dict()
                output_files.append(output_files_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "status": status,
            }
        )
        if output is not UNSET:
            field_dict["output"] = output
        if output_files is not UNSET:
            field_dict["output_files"] = output_files

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.output_file_info import OutputFileInfo
        from ..models.sample_job_output import SampleJobOutput

        d = dict(src_dict)
        status = JobStatus(d.pop("status"))

        def _parse_output(data: object) -> None | SampleJobOutput | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                output_type_0 = SampleJobOutput.from_dict(data)

                return output_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | SampleJobOutput | Unset, data)

        output = _parse_output(d.pop("output", UNSET))

        _output_files = d.pop("output_files", UNSET)
        output_files: list[OutputFileInfo] | Unset = UNSET
        if _output_files is not UNSET:
            output_files = []
            for output_files_item_data in _output_files:
                output_files_item = OutputFileInfo.from_dict(output_files_item_data)

                output_files.append(output_files_item)

        sample_job_result_response = cls(
            status=status,
            output=output,
            output_files=output_files,
        )

        sample_job_result_response.additional_properties = d
        return sample_job_result_response

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
