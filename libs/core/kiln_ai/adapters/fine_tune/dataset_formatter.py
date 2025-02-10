import json
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Protocol
from uuid import uuid4

from kiln_ai.adapters.model_adapters.base_adapter import COT_FINAL_ANSWER_PROMPT
from kiln_ai.datamodel import DatasetSplit, FinetuneDataStrategy, TaskRun


class DatasetFormat(str, Enum):
    """Formats for dataset generation. Both for file format (like JSONL), and internal structure (like chat/toolcall)"""

    """OpenAI chat format with plaintext response"""
    OPENAI_CHAT_JSONL = "openai_chat_jsonl"

    """OpenAI chat format with json response_format"""
    OPENAI_CHAT_JSON_SCHEMA_JSONL = "openai_chat_json_schema_jsonl"

    """OpenAI chat format with tool call response"""
    OPENAI_CHAT_TOOLCALL_JSONL = "openai_chat_toolcall_jsonl"

    """HuggingFace chat template in JSONL"""
    HUGGINGFACE_CHAT_TEMPLATE_JSONL = "huggingface_chat_template_jsonl"

    """HuggingFace chat template with tool calls in JSONL"""
    HUGGINGFACE_CHAT_TEMPLATE_TOOLCALL_JSONL = (
        "huggingface_chat_template_toolcall_jsonl"
    )

    """Vertex Gemini 1.5 format (flash and pro)"""
    VERTEX_GEMINI_1_5 = "vertex_gemini_1_5"


@dataclass
class ModelTrainingData:
    input: str
    system_message: str
    final_output: str
    # These 3 are optional, and used for COT/Thinking style multi-message responses
    thinking_instructions: str | None = None
    thinking: str | None = None
    thinking_final_answer_prompt: str | None = None

    def supports_cot(self) -> bool:
        return (
            self.thinking_instructions is not None
            and self.thinking is not None
            and self.thinking_final_answer_prompt is not None
        )


class FormatGenerator(Protocol):
    """Protocol for format generators"""

    def __call__(
        self,
        training_data: ModelTrainingData,
    ) -> Dict[str, Any]: ...


def build_training_data(
    task_run: TaskRun,
    system_message: str,
    include_cot: bool,
    thinking_instructions: str | None = None,
) -> ModelTrainingData:
    """
    Generate data for training.

    For final output, get the best task output from the task run, preferring repaired output if available.

    For thinking, get the intermediate output if it exists, otherwise return None.
    """
    final_output = task_run.output.output
    if task_run.repaired_output is not None:
        final_output = task_run.repaired_output.output

    thinking = None
    thinking_final_answer_prompt = None
    parent_task = task_run.parent_task()

    if include_cot and task_run.has_thinking_training_data():
        if not parent_task:
            raise ValueError(
                "TaskRuns for training required a parent Task for building a chain of thought prompts. Train without COT, or save this TaskRun to a parent Task."
            )

        # Prefer reasoning to cot if both are present
        intermediate_outputs = task_run.intermediate_outputs or {}
        thinking = intermediate_outputs.get("reasoning") or intermediate_outputs.get(
            "chain_of_thought"
        )

        thinking_final_answer_prompt = COT_FINAL_ANSWER_PROMPT

        # Always use the passed thinking instructions, but check they are present for COT
        if not thinking_instructions:
            raise ValueError(
                "Thinking instructions are required when data_strategy is final_and_intermediate"
            )

    return ModelTrainingData(
        input=task_run.input,
        system_message=system_message,
        final_output=final_output,
        thinking=thinking,
        thinking_instructions=thinking_instructions,
        thinking_final_answer_prompt=thinking_final_answer_prompt,
    )


def generate_chat_message_response(
    training_data: ModelTrainingData,
) -> Dict[str, Any]:
    """Generate OpenAI chat format with plaintext response"""

    messages: list[dict[str, str | None]] = [
        {"role": "system", "content": training_data.system_message},
        {"role": "user", "content": training_data.input},
    ]

    if training_data.supports_cot():
        messages.extend(
            [
                {"role": "user", "content": training_data.thinking_instructions},
                {"role": "assistant", "content": training_data.thinking},
                {
                    "role": "user",
                    "content": training_data.thinking_final_answer_prompt,
                },
            ]
        )

    messages.append({"role": "assistant", "content": training_data.final_output})

    return {"messages": messages}


def generate_json_schema_message(
    training_data: ModelTrainingData,
) -> Dict[str, Any]:
    """Generate OpenAI chat format with validated JSON response"""
    # Load and dump to ensure it's valid JSON and goes to 1 line
    try:
        json_data = json.loads(training_data.final_output)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Invalid JSON in JSON Schema training set: {e}\nOutput Data: {training_data.final_output}"
        ) from e
    json_string = json.dumps(json_data, ensure_ascii=False)

    messages: list[dict[str, str | None]] = [
        {"role": "system", "content": training_data.system_message},
        {"role": "user", "content": training_data.input},
    ]

    if training_data.supports_cot():
        messages.extend(
            [
                {"role": "user", "content": training_data.thinking_instructions},
                {"role": "assistant", "content": training_data.thinking},
                {
                    "role": "user",
                    "content": training_data.thinking_final_answer_prompt,
                },
            ]
        )

    messages.append({"role": "assistant", "content": json_string})

    return {"messages": messages}


def generate_chat_message_toolcall(
    training_data: ModelTrainingData,
) -> Dict[str, Any]:
    """Generate OpenAI chat format with tool call response"""
    try:
        arguments = json.loads(training_data.final_output)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in for tool call: {e}") from e

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": training_data.system_message},
        {"role": "user", "content": training_data.input},
    ]

    if training_data.supports_cot():
        messages.extend(
            [
                {"role": "user", "content": training_data.thinking_instructions},
                {"role": "assistant", "content": training_data.thinking},
                {
                    "role": "user",
                    "content": training_data.thinking_final_answer_prompt,
                },
            ]
        )

    messages.append(
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "task_response",
                        # Yes we parse then dump again. This ensures it's valid JSON, and ensures it goes to 1 line
                        "arguments": json.dumps(arguments, ensure_ascii=False),
                    },
                }
            ],
        },
    )

    return {"messages": messages}


def generate_huggingface_chat_template(
    training_data: ModelTrainingData,
) -> Dict[str, Any]:
    """Generate HuggingFace chat template"""

    conversations: list[dict[str, Any]] = [
        {"role": "system", "content": training_data.system_message},
        {"role": "user", "content": training_data.input},
    ]

    if training_data.supports_cot():
        conversations.extend(
            [
                {"role": "user", "content": training_data.thinking_instructions},
                {"role": "assistant", "content": training_data.thinking},
                {"role": "user", "content": training_data.thinking_final_answer_prompt},
            ]
        )

    conversations.append({"role": "assistant", "content": training_data.final_output})

    return {"conversations": conversations}


def generate_huggingface_chat_template_toolcall(
    training_data: ModelTrainingData,
) -> Dict[str, Any]:
    """Generate HuggingFace chat template with tool calls"""
    try:
        arguments = json.loads(training_data.final_output)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in for tool call: {e}") from e

    # See https://huggingface.co/docs/transformers/en/chat_templating
    conversations: list[dict[str, Any]] = [
        {"role": "system", "content": training_data.system_message},
        {"role": "user", "content": training_data.input},
    ]

    if training_data.supports_cot():
        conversations.extend(
            [
                {"role": "user", "content": training_data.thinking_instructions},
                {"role": "assistant", "content": training_data.thinking},
                {"role": "user", "content": training_data.thinking_final_answer_prompt},
            ]
        )

    conversations.append(
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "type": "function",
                    "function": {
                        "name": "task_response",
                        "id": str(uuid4()).replace("-", "")[:9],
                        "arguments": arguments,
                    },
                }
            ],
        },
    )

    return {"conversations": conversations}


def generate_vertex_gemini_1_5(
    training_data: ModelTrainingData,
) -> Dict[str, Any]:
    """Generate Vertex Gemini 1.5 format (flash and pro)"""
    # See https://cloud.google.com/vertex-ai/generative-ai/docs/models/gemini-supervised-tuning-prepare

    contents = [
        {
            "role": "user",
            "parts": [
                {
                    "text": training_data.input,
                }
            ],
        }
    ]

    if training_data.supports_cot():
        contents.extend(
            [
                {
                    "role": "user",
                    "parts": [{"text": training_data.thinking_instructions}],
                },
                {"role": "model", "parts": [{"text": training_data.thinking}]},
                {
                    "role": "user",
                    "parts": [{"text": training_data.thinking_final_answer_prompt}],
                },
            ]
        )

    contents.append(
        {
            "role": "model",
            "parts": [{"text": training_data.final_output}],
        }
    )

    return {
        "systemInstruction": {
            "role": "system",
            "parts": [
                {
                    "text": training_data.system_message,
                }
            ],
        },
        "contents": contents,
    }


FORMAT_GENERATORS: Dict[DatasetFormat, FormatGenerator] = {
    DatasetFormat.OPENAI_CHAT_JSONL: generate_chat_message_response,
    DatasetFormat.OPENAI_CHAT_JSON_SCHEMA_JSONL: generate_json_schema_message,
    DatasetFormat.OPENAI_CHAT_TOOLCALL_JSONL: generate_chat_message_toolcall,
    DatasetFormat.HUGGINGFACE_CHAT_TEMPLATE_JSONL: generate_huggingface_chat_template,
    DatasetFormat.HUGGINGFACE_CHAT_TEMPLATE_TOOLCALL_JSONL: generate_huggingface_chat_template_toolcall,
    DatasetFormat.VERTEX_GEMINI_1_5: generate_vertex_gemini_1_5,
}


class DatasetFormatter:
    """Handles formatting of datasets into various output formats"""

    def __init__(
        self,
        dataset: DatasetSplit,
        system_message: str,
        thinking_instructions: str | None = None,
    ):
        self.dataset = dataset
        self.system_message = system_message
        self.thinking_instructions = thinking_instructions

        task = dataset.parent_task()
        if task is None:
            raise ValueError("Dataset has no parent task")
        self.task = task

    def dump_to_file(
        self,
        split_name: str,
        format_type: DatasetFormat,
        data_strategy: FinetuneDataStrategy,
        path: Path | None = None,
    ) -> Path:
        """
        Format the dataset into the specified format.

        Args:
            split_name: Name of the split to dump
            format_type: Format to generate the dataset in
            path: Optional path to write to. If None, writes to temp directory

        Returns:
            Path to the generated file

        Note:
            The output is written in UTF-8 encoding with ensure_ascii=False to properly
            support international text content while maintaining readability.
        """
        if format_type not in FORMAT_GENERATORS:
            raise ValueError(f"Unsupported format: {format_type}")
        if split_name not in self.dataset.split_contents:
            raise ValueError(f"Split {split_name} not found in dataset")

        generator = FORMAT_GENERATORS[format_type]

        include_cot = data_strategy == FinetuneDataStrategy.final_and_intermediate

        # Write to a temp file if no path is provided
        output_path = (
            path
            or Path(tempfile.gettempdir())
            / f"{self.dataset.name} -- split-{split_name} -- format-{format_type.value} -- {'cot' if include_cot else 'no-cot'}.jsonl"
        )

        runs = self.task.runs()
        runs_by_id = {run.id: run for run in runs}

        # Generate formatted output with UTF-8 encoding
        with open(output_path, "w", encoding="utf-8") as f:
            for run_id in self.dataset.split_contents[split_name]:
                task_run = runs_by_id[run_id]
                if task_run is None:
                    raise ValueError(
                        f"Task run {run_id} not found. This is required by this dataset."
                    )

                training_data = build_training_data(
                    task_run=task_run,
                    system_message=self.system_message,
                    include_cot=include_cot,
                    thinking_instructions=self.thinking_instructions,
                )
                example = generator(training_data)
                # Allow non-ascii characters in the dataset.
                # Better readability for non-English users. If you don't support UTF-8... you should.
                f.write(json.dumps(example, ensure_ascii=False) + "\n")

        return output_path
