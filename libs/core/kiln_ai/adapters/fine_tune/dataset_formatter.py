import json
import tempfile
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Protocol
from uuid import uuid4

from kiln_ai.datamodel import DatasetSplit, TaskRun


class DatasetFormat(str, Enum):
    """Formats for dataset generation. Both for file format (like JSONL), and internal structure (like chat/toolcall)"""

    """OpenAI chat format with plaintext response"""
    OPENAI_CHAT_JSONL = "openai_chat_jsonl"

    """OpenAI chat format with tool call response"""
    OPENAI_CHAT_TOOLCALL_JSONL = "openai_chat_toolcall_jsonl"

    """HuggingFace chat template in JSONL"""
    HUGGINGFACE_CHAT_TEMPLATE_JSONL = "huggingface_chat_template_jsonl"

    """HuggingFace chat template with tool calls in JSONL"""
    HUGGINGFACE_CHAT_TEMPLATE_TOOLCALL_JSONL = (
        "huggingface_chat_template_toolcall_jsonl"
    )

    """Fireworks Llama 3.1 tool call. Custom format to work with our Fireworks jinja templates"""
    FIREWORKS_LLAMA_3_1_TOOLCALL_JSONL = "fireworks_llama_3_1_toolcall_jsonl"

    """Fireworks Llama 3.2 tool call. Custom format to work with our Fireworks jinja templates"""
    FIREWORKS_LLAMA_3_2_TOOLCALL_JSONL = "fireworks_llama_3_2_toolcall_jsonl"


class FormatGenerator(Protocol):
    """Protocol for format generators"""

    def __call__(self, task_run: TaskRun, system_message: str) -> Dict[str, Any]: ...


def generate_chat_message_response(
    task_run: TaskRun, system_message: str
) -> Dict[str, Any]:
    """Generate OpenAI chat format with plaintext response"""
    return {
        "messages": [
            {"role": "system", "content": system_message},
            {"role": "user", "content": task_run.input},
            {"role": "assistant", "content": task_run.output.output},
        ]
    }


def generate_chat_message_toolcall(
    task_run: TaskRun, system_message: str
) -> Dict[str, Any]:
    """Generate OpenAI chat format with tool call response"""
    try:
        arguments = json.loads(task_run.output.output)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in for tool call: {e}") from e

    return {
        "messages": [
            {"role": "system", "content": system_message},
            {"role": "user", "content": task_run.input},
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
                            "arguments": json.dumps(arguments),
                        },
                    }
                ],
            },
        ]
    }


def generate_llama_3_1_tool_call(
    task_run: TaskRun, system_message: str
) -> Dict[str, Any]:
    """Generate partitioned tool call for use with Fireworks jinja templates"""

    try:
        arguments = json.loads(task_run.output.output)
        # Parse and pretty print the schema
        schema = json.loads(task_run.parent_task().output_json_schema)
        schema_parameters = {}
        for param_name, param_info in schema["properties"].items():
            schema_parameters[param_name] = {
                "type": param_info["type"],
                "description": param_info.get("description", ""),
                "required": param_name in schema["required"],
            }
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in for tool call or schema: {e}") from e
    return {
        "messages": [
            {
                "role": "system",
                "content": system_message,
                "tool_call_schema": json.dumps(
                    {
                        "name": "task_response",
                        # "description": "This function is used to respond to the user query.",
                        "parameters": schema_parameters,
                    },
                    indent=2,
                ),
            },
            {
                "role": "user",
                "content": task_run.input,
            },
            {
                "role": "assistant",
                "content": None,
                # Yes we parse then dump again. This ensures it's valid JSON, and ensures it goes to 1 line
                "tool_call_json": json.dumps(arguments),
            },
        ]
    }


def generate_llama_3_2_tool_call(
    task_run: TaskRun, system_message: str
) -> Dict[str, Any]:
    """Generate partitioned tool call for use with Fireworks jinja templates"""
    try:
        arguments = json.loads(task_run.output.output)
        # Parse and pretty print the schema
        schema = json.loads(task_run.parent_task().output_json_schema)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in for tool call or schema: {e}") from e

    # Format arguments as Python-style function call
    formatted_args = ", ".join(f"{k}: {json.dumps(v)}" for k, v in arguments.items())
    tool_call = f"[task_response({formatted_args})]"

    return {
        "messages": [
            {
                "role": "system",
                "content": system_message,
                "tool_call_schema": json.dumps(
                    {
                        "name": "task_response",
                        "parameters": {
                            "type": "dict",
                            "properties": schema["properties"],
                            "required": schema["required"],
                        },
                    },
                    indent=2,
                ),
            },
            {
                "role": "user",
                "content": task_run.input,
            },
            {
                "role": "assistant",
                "content": None,
                "tool_call": tool_call,  # Use the formatted tool call string instead of JSON
            },
        ]
    }


def generate_huggingface_chat_template(
    task_run: TaskRun, system_message: str
) -> Dict[str, Any]:
    """Generate HuggingFace chat template"""
    return {
        "conversations": [
            {"role": "system", "content": system_message},
            {"role": "user", "content": task_run.input},
            {"role": "assistant", "content": task_run.output.output},
        ]
    }


def generate_huggingface_chat_template_toolcall(
    task_run: TaskRun, system_message: str
) -> Dict[str, Any]:
    """Generate HuggingFace chat template with tool calls"""
    try:
        arguments = json.loads(task_run.output.output)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in for tool call: {e}") from e

    # See https://huggingface.co/docs/transformers/en/chat_templating
    return {
        "conversations": [
            {"role": "system", "content": system_message},
            {"role": "user", "content": task_run.input},
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
        ]
    }


FORMAT_GENERATORS: Dict[DatasetFormat, FormatGenerator] = {
    DatasetFormat.OPENAI_CHAT_JSONL: generate_chat_message_response,
    DatasetFormat.OPENAI_CHAT_TOOLCALL_JSONL: generate_chat_message_toolcall,
    DatasetFormat.HUGGINGFACE_CHAT_TEMPLATE_JSONL: generate_huggingface_chat_template,
    DatasetFormat.HUGGINGFACE_CHAT_TEMPLATE_TOOLCALL_JSONL: generate_huggingface_chat_template_toolcall,
    DatasetFormat.FIREWORKS_LLAMA_3_1_TOOLCALL_JSONL: generate_llama_3_1_tool_call,
    DatasetFormat.FIREWORKS_LLAMA_3_2_TOOLCALL_JSONL: generate_llama_3_2_tool_call,
}


class DatasetFormatter:
    """Handles formatting of datasets into various output formats"""

    def __init__(self, dataset: DatasetSplit, system_message: str):
        self.dataset = dataset
        self.system_message = system_message

        task = dataset.parent_task()
        if task is None:
            raise ValueError("Dataset has no parent task")
        self.task = task

    def dump_to_file(
        self, split_name: str, format_type: DatasetFormat, path: Path | None = None
    ) -> Path:
        """
        Format the dataset into the specified format.

        Args:
            split_name: Name of the split to dump
            format_type: Format to generate the dataset in
            path: Optional path to write to. If None, writes to temp directory

        Returns:
            Path to the generated file
        """
        if format_type not in FORMAT_GENERATORS:
            raise ValueError(f"Unsupported format: {format_type}")
        if split_name not in self.dataset.split_contents:
            raise ValueError(f"Split {split_name} not found in dataset")

        generator = FORMAT_GENERATORS[format_type]

        # Write to a temp file if no path is provided
        output_path = (
            path
            or Path(tempfile.gettempdir())
            / f"{self.dataset.name}_{split_name}_{format_type}.jsonl"
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

                example = generator(task_run, self.system_message)
                f.write(json.dumps(example) + "\n")

        return output_path
