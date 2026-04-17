from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.chat_completion_assistant_message_param_wrapper import ChatCompletionAssistantMessageParamWrapper
    from ..models.chat_completion_developer_message_param import ChatCompletionDeveloperMessageParam
    from ..models.chat_completion_function_message_param import ChatCompletionFunctionMessageParam
    from ..models.chat_completion_system_message_param import ChatCompletionSystemMessageParam
    from ..models.chat_completion_tool_message_param_wrapper import ChatCompletionToolMessageParamWrapper
    from ..models.chat_completion_user_message_param import ChatCompletionUserMessageParam
    from ..models.data_source import DataSource
    from ..models.task_output import TaskOutput
    from ..models.task_run_intermediate_outputs_type_0 import TaskRunIntermediateOutputsType0
    from ..models.usage import Usage


T = TypeVar("T", bound="TaskRun")


@_attrs_define
class TaskRun:
    """Represents a single execution of a Task.

    Contains the input used, its source, the output produced, and optional
    repair information if the output needed correction.

        Attributes:
            input_ (str): The inputs to the task. JSON formatted for structured input, plaintext for unstructured input.
            output (TaskOutput): An output for a specific task run.

                Contains the actual output content, its source (human or synthetic),
                and optional rating information.
            model_type (str):
            v (int | Unset): Schema version for migration support. Default: 1.
            id (None | str | Unset): Unique identifier for this record.
            path (None | str | Unset): File system path where the record is stored.
            created_at (datetime.datetime | Unset): Timestamp when the model was created.
            created_by (str | Unset): User ID of the creator.
            input_source (DataSource | None | Unset): The source of the input: human or synthetic.
            repair_instructions (None | str | Unset): Instructions for fixing the output. Should define what is wrong, and
                how to fix it. Will be used by models for both generating a fixed output, and evaluating future models.
            user_feedback (None | str | Unset): User feedback from the spec review process explaining why the output passes
                or fails a requirement.
            repaired_output (None | TaskOutput | Unset): An version of the output with issues fixed. This must be a 'fixed'
                version of the existing output, and not an entirely new output. If you wish to generate an ideal curatorial
                output for this task unrelated to this output, generate a new TaskOutput with type 'human' instead of using this
                field.
            intermediate_outputs (None | TaskRunIntermediateOutputsType0 | Unset): Intermediate outputs from the task run.
                Keys are the names of the intermediate output steps (cot=chain of thought, etc), values are the output data.
            tags (list[str] | Unset): Tags for the task run. Tags are used to categorize task runs for filtering and
                reporting.
            usage (None | Unset | Usage): Usage information for the task run. This includes the number of input tokens,
                output tokens, and total tokens used.
            trace (list[ChatCompletionAssistantMessageParamWrapper | ChatCompletionDeveloperMessageParam |
                ChatCompletionFunctionMessageParam | ChatCompletionSystemMessageParam | ChatCompletionToolMessageParamWrapper |
                ChatCompletionUserMessageParam] | None | Unset): The trace of the task run in OpenAI format. This is the list of
                messages that were sent to/from the model.
            parent_task_run_id (None | str | Unset): The ID of the parent task run. This is the ID of the task run that
                contains this task run.
    """

    input_: str
    output: TaskOutput
    model_type: str
    v: int | Unset = 1
    id: None | str | Unset = UNSET
    path: None | str | Unset = UNSET
    created_at: datetime.datetime | Unset = UNSET
    created_by: str | Unset = UNSET
    input_source: DataSource | None | Unset = UNSET
    repair_instructions: None | str | Unset = UNSET
    user_feedback: None | str | Unset = UNSET
    repaired_output: None | TaskOutput | Unset = UNSET
    intermediate_outputs: None | TaskRunIntermediateOutputsType0 | Unset = UNSET
    tags: list[str] | Unset = UNSET
    usage: None | Unset | Usage = UNSET
    trace: (
        list[
            ChatCompletionAssistantMessageParamWrapper
            | ChatCompletionDeveloperMessageParam
            | ChatCompletionFunctionMessageParam
            | ChatCompletionSystemMessageParam
            | ChatCompletionToolMessageParamWrapper
            | ChatCompletionUserMessageParam
        ]
        | None
        | Unset
    ) = UNSET
    parent_task_run_id: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.chat_completion_assistant_message_param_wrapper import ChatCompletionAssistantMessageParamWrapper
        from ..models.chat_completion_developer_message_param import ChatCompletionDeveloperMessageParam
        from ..models.chat_completion_system_message_param import ChatCompletionSystemMessageParam
        from ..models.chat_completion_tool_message_param_wrapper import ChatCompletionToolMessageParamWrapper
        from ..models.chat_completion_user_message_param import ChatCompletionUserMessageParam
        from ..models.data_source import DataSource
        from ..models.task_output import TaskOutput
        from ..models.task_run_intermediate_outputs_type_0 import TaskRunIntermediateOutputsType0
        from ..models.usage import Usage

        input_ = self.input_

        output = self.output.to_dict()

        model_type = self.model_type

        v = self.v

        id: None | str | Unset
        if isinstance(self.id, Unset):
            id = UNSET
        else:
            id = self.id

        path: None | str | Unset
        if isinstance(self.path, Unset):
            path = UNSET
        else:
            path = self.path

        created_at: str | Unset = UNSET
        if not isinstance(self.created_at, Unset):
            created_at = self.created_at.isoformat()

        created_by = self.created_by

        input_source: dict[str, Any] | None | Unset
        if isinstance(self.input_source, Unset):
            input_source = UNSET
        elif isinstance(self.input_source, DataSource):
            input_source = self.input_source.to_dict()
        else:
            input_source = self.input_source

        repair_instructions: None | str | Unset
        if isinstance(self.repair_instructions, Unset):
            repair_instructions = UNSET
        else:
            repair_instructions = self.repair_instructions

        user_feedback: None | str | Unset
        if isinstance(self.user_feedback, Unset):
            user_feedback = UNSET
        else:
            user_feedback = self.user_feedback

        repaired_output: dict[str, Any] | None | Unset
        if isinstance(self.repaired_output, Unset):
            repaired_output = UNSET
        elif isinstance(self.repaired_output, TaskOutput):
            repaired_output = self.repaired_output.to_dict()
        else:
            repaired_output = self.repaired_output

        intermediate_outputs: dict[str, Any] | None | Unset
        if isinstance(self.intermediate_outputs, Unset):
            intermediate_outputs = UNSET
        elif isinstance(self.intermediate_outputs, TaskRunIntermediateOutputsType0):
            intermediate_outputs = self.intermediate_outputs.to_dict()
        else:
            intermediate_outputs = self.intermediate_outputs

        tags: list[str] | Unset = UNSET
        if not isinstance(self.tags, Unset):
            tags = self.tags

        usage: dict[str, Any] | None | Unset
        if isinstance(self.usage, Unset):
            usage = UNSET
        elif isinstance(self.usage, Usage):
            usage = self.usage.to_dict()
        else:
            usage = self.usage

        trace: list[dict[str, Any]] | None | Unset
        if isinstance(self.trace, Unset):
            trace = UNSET
        elif isinstance(self.trace, list):
            trace = []
            for trace_type_0_item_data in self.trace:
                trace_type_0_item: dict[str, Any]
                if isinstance(trace_type_0_item_data, ChatCompletionDeveloperMessageParam):
                    trace_type_0_item = trace_type_0_item_data.to_dict()
                elif isinstance(trace_type_0_item_data, ChatCompletionSystemMessageParam):
                    trace_type_0_item = trace_type_0_item_data.to_dict()
                elif isinstance(trace_type_0_item_data, ChatCompletionUserMessageParam):
                    trace_type_0_item = trace_type_0_item_data.to_dict()
                elif isinstance(trace_type_0_item_data, ChatCompletionAssistantMessageParamWrapper):
                    trace_type_0_item = trace_type_0_item_data.to_dict()
                elif isinstance(trace_type_0_item_data, ChatCompletionToolMessageParamWrapper):
                    trace_type_0_item = trace_type_0_item_data.to_dict()
                else:
                    trace_type_0_item = trace_type_0_item_data.to_dict()

                trace.append(trace_type_0_item)

        else:
            trace = self.trace

        parent_task_run_id: None | str | Unset
        if isinstance(self.parent_task_run_id, Unset):
            parent_task_run_id = UNSET
        else:
            parent_task_run_id = self.parent_task_run_id

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "input": input_,
                "output": output,
                "model_type": model_type,
            }
        )
        if v is not UNSET:
            field_dict["v"] = v
        if id is not UNSET:
            field_dict["id"] = id
        if path is not UNSET:
            field_dict["path"] = path
        if created_at is not UNSET:
            field_dict["created_at"] = created_at
        if created_by is not UNSET:
            field_dict["created_by"] = created_by
        if input_source is not UNSET:
            field_dict["input_source"] = input_source
        if repair_instructions is not UNSET:
            field_dict["repair_instructions"] = repair_instructions
        if user_feedback is not UNSET:
            field_dict["user_feedback"] = user_feedback
        if repaired_output is not UNSET:
            field_dict["repaired_output"] = repaired_output
        if intermediate_outputs is not UNSET:
            field_dict["intermediate_outputs"] = intermediate_outputs
        if tags is not UNSET:
            field_dict["tags"] = tags
        if usage is not UNSET:
            field_dict["usage"] = usage
        if trace is not UNSET:
            field_dict["trace"] = trace
        if parent_task_run_id is not UNSET:
            field_dict["parent_task_run_id"] = parent_task_run_id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.chat_completion_assistant_message_param_wrapper import ChatCompletionAssistantMessageParamWrapper
        from ..models.chat_completion_developer_message_param import ChatCompletionDeveloperMessageParam
        from ..models.chat_completion_function_message_param import ChatCompletionFunctionMessageParam
        from ..models.chat_completion_system_message_param import ChatCompletionSystemMessageParam
        from ..models.chat_completion_tool_message_param_wrapper import ChatCompletionToolMessageParamWrapper
        from ..models.chat_completion_user_message_param import ChatCompletionUserMessageParam
        from ..models.data_source import DataSource
        from ..models.task_output import TaskOutput
        from ..models.task_run_intermediate_outputs_type_0 import TaskRunIntermediateOutputsType0
        from ..models.usage import Usage

        d = dict(src_dict)
        input_ = d.pop("input")

        output = TaskOutput.from_dict(d.pop("output"))

        model_type = d.pop("model_type")

        v = d.pop("v", UNSET)

        def _parse_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        id = _parse_id(d.pop("id", UNSET))

        def _parse_path(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        path = _parse_path(d.pop("path", UNSET))

        _created_at = d.pop("created_at", UNSET)
        created_at: datetime.datetime | Unset
        if isinstance(_created_at, Unset):
            created_at = UNSET
        else:
            created_at = isoparse(_created_at)

        created_by = d.pop("created_by", UNSET)

        def _parse_input_source(data: object) -> DataSource | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                input_source_type_0 = DataSource.from_dict(data)

                return input_source_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(DataSource | None | Unset, data)

        input_source = _parse_input_source(d.pop("input_source", UNSET))

        def _parse_repair_instructions(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        repair_instructions = _parse_repair_instructions(d.pop("repair_instructions", UNSET))

        def _parse_user_feedback(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        user_feedback = _parse_user_feedback(d.pop("user_feedback", UNSET))

        def _parse_repaired_output(data: object) -> None | TaskOutput | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                repaired_output_type_0 = TaskOutput.from_dict(data)

                return repaired_output_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | TaskOutput | Unset, data)

        repaired_output = _parse_repaired_output(d.pop("repaired_output", UNSET))

        def _parse_intermediate_outputs(data: object) -> None | TaskRunIntermediateOutputsType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                intermediate_outputs_type_0 = TaskRunIntermediateOutputsType0.from_dict(data)

                return intermediate_outputs_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | TaskRunIntermediateOutputsType0 | Unset, data)

        intermediate_outputs = _parse_intermediate_outputs(d.pop("intermediate_outputs", UNSET))

        tags = cast(list[str], d.pop("tags", UNSET))

        def _parse_usage(data: object) -> None | Unset | Usage:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                usage_type_0 = Usage.from_dict(data)

                return usage_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | Usage, data)

        usage = _parse_usage(d.pop("usage", UNSET))

        def _parse_trace(
            data: object,
        ) -> (
            list[
                ChatCompletionAssistantMessageParamWrapper
                | ChatCompletionDeveloperMessageParam
                | ChatCompletionFunctionMessageParam
                | ChatCompletionSystemMessageParam
                | ChatCompletionToolMessageParamWrapper
                | ChatCompletionUserMessageParam
            ]
            | None
            | Unset
        ):
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                trace_type_0 = []
                _trace_type_0 = data
                for trace_type_0_item_data in _trace_type_0:

                    def _parse_trace_type_0_item(
                        data: object,
                    ) -> (
                        ChatCompletionAssistantMessageParamWrapper
                        | ChatCompletionDeveloperMessageParam
                        | ChatCompletionFunctionMessageParam
                        | ChatCompletionSystemMessageParam
                        | ChatCompletionToolMessageParamWrapper
                        | ChatCompletionUserMessageParam
                    ):
                        try:
                            if not isinstance(data, dict):
                                raise TypeError()
                            trace_type_0_item_type_0 = ChatCompletionDeveloperMessageParam.from_dict(data)

                            return trace_type_0_item_type_0
                        except (TypeError, ValueError, AttributeError, KeyError):
                            pass
                        try:
                            if not isinstance(data, dict):
                                raise TypeError()
                            trace_type_0_item_type_1 = ChatCompletionSystemMessageParam.from_dict(data)

                            return trace_type_0_item_type_1
                        except (TypeError, ValueError, AttributeError, KeyError):
                            pass
                        try:
                            if not isinstance(data, dict):
                                raise TypeError()
                            trace_type_0_item_type_2 = ChatCompletionUserMessageParam.from_dict(data)

                            return trace_type_0_item_type_2
                        except (TypeError, ValueError, AttributeError, KeyError):
                            pass
                        try:
                            if not isinstance(data, dict):
                                raise TypeError()
                            trace_type_0_item_type_3 = ChatCompletionAssistantMessageParamWrapper.from_dict(data)

                            return trace_type_0_item_type_3
                        except (TypeError, ValueError, AttributeError, KeyError):
                            pass
                        try:
                            if not isinstance(data, dict):
                                raise TypeError()
                            trace_type_0_item_type_4 = ChatCompletionToolMessageParamWrapper.from_dict(data)

                            return trace_type_0_item_type_4
                        except (TypeError, ValueError, AttributeError, KeyError):
                            pass
                        if not isinstance(data, dict):
                            raise TypeError()
                        trace_type_0_item_type_5 = ChatCompletionFunctionMessageParam.from_dict(data)

                        return trace_type_0_item_type_5

                    trace_type_0_item = _parse_trace_type_0_item(trace_type_0_item_data)

                    trace_type_0.append(trace_type_0_item)

                return trace_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(
                list[
                    ChatCompletionAssistantMessageParamWrapper
                    | ChatCompletionDeveloperMessageParam
                    | ChatCompletionFunctionMessageParam
                    | ChatCompletionSystemMessageParam
                    | ChatCompletionToolMessageParamWrapper
                    | ChatCompletionUserMessageParam
                ]
                | None
                | Unset,
                data,
            )

        trace = _parse_trace(d.pop("trace", UNSET))

        def _parse_parent_task_run_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        parent_task_run_id = _parse_parent_task_run_id(d.pop("parent_task_run_id", UNSET))

        task_run = cls(
            input_=input_,
            output=output,
            model_type=model_type,
            v=v,
            id=id,
            path=path,
            created_at=created_at,
            created_by=created_by,
            input_source=input_source,
            repair_instructions=repair_instructions,
            user_feedback=user_feedback,
            repaired_output=repaired_output,
            intermediate_outputs=intermediate_outputs,
            tags=tags,
            usage=usage,
            trace=trace,
            parent_task_run_id=parent_task_run_id,
        )

        task_run.additional_properties = d
        return task_run

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
