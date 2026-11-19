"""Paid provider checks for the improve-reasoning project.

Run from the repo root, with keys loaded from .env:

    set -a; . ./.env; set +a
    uv run python specs/projects/improve_reasoning/research/provider-verification/probe.py q1

Each section writes trimmed results to $TMPDIR/kiln_pv_raw/<section>.json.
`probe.py bundle` gathers them into raw_results.json.gz next to this file.
Kiln settings are redirected to a temporary file, so real settings are untouched.
"""

from __future__ import annotations

import asyncio
import copy
import gzip
import json
import os
import sys
import tempfile
import time
import warnings
from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx
import litellm
from kiln_ai.adapters.adapter_registry import litellm_core_provider_config
from kiln_ai.adapters.litellm_utils.litellm_streaming import StreamingCompletion
from kiln_ai.adapters.ml_model_list import ModelProviderName, StructuredOutputMode
from kiln_ai.adapters.model_adapters import adapter_stream
from kiln_ai.adapters.model_adapters.base_adapter import AdapterConfig
from kiln_ai.adapters.model_adapters.litellm_adapter import LiteLlmAdapter
from kiln_ai.adapters.model_adapters.litellm_config import LiteLlmConfig
from kiln_ai.datamodel import Project, PromptGenerators, Task
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties, ToolsRunConfig
from kiln_ai.datamodel.tool_id import KilnBuiltInToolId
from kiln_ai.utils.config import Config
from litellm.integrations.custom_logger import CustomLogger

HERE = Path(__file__).resolve().parent
RAW_DIR = Path(os.environ.get("TMPDIR", tempfile.gettempdir())) / "kiln_pv_raw"

INSTRUCTION = (
    "Think about it hard! Solve the math problem provided by the user, in a step by "
    "step manner. Use the tools provided to solve the math problem. Then use the "
    "result in a short sentence about a cat going to the mall. Remember to use the "
    "tools for math even if the operation looks easy."
)
PROMPT = (
    "A bakery sells muffins at $3.75 and cookies at $1.40. On Monday it sold 140 "
    "muffins and 264 cookies. On Tuesday it sold 25% fewer muffins and 22 more "
    "cookies than on Monday. How much more revenue did Monday make than Tuesday? "
    "Plan carefully. Use the tools for every arithmetic step and call one tool at a "
    "time, because each step needs the result of the step before it."
)
ANSWER = "100.45"
FOLLOW_UP = "What was the result? Reply in one short sentence."

TRIM_KEYS = {
    "signature",
    "data",
    "encrypted_content",
    "thought_signature",
    "thoughtSignature",
    "thought_signatures",
}
LONG_TEXT_KEYS = {"content", "text", "system", "instruction"}


def trim(value: Any, key: str | None = None) -> Any:
    """Cut signatures and encrypted blobs to 40 characters, and long prompt text to
    300, so the raw data stays small and holds no replayable reasoning state."""
    if isinstance(value, dict):
        return {k: trim(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [trim(v, key) for v in value]
    if isinstance(value, str):
        if key in TRIM_KEYS and len(value) > 40:
            return value[:40] + f"...[{len(value)} chars]"
        marker = value.find("__thought__")
        if marker >= 0 and len(value) > marker + 51:
            return value[: marker + 51] + f"...[{len(value)} chars]"
        if key in LONG_TEXT_KEYS and len(value) > 1500:
            return value[:300] + f"...[{len(value)} chars]"
    return value


def to_jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


def dump_message(message: Any) -> dict[str, Any]:
    """The JSON round-trip of model_dump(exclude_none=True), as a saved trace would hold it."""
    return to_jsonable(message.model_dump(exclude_none=True))


class Recorder(CustomLogger):
    """Captures every provider request body, Kiln's completion kwargs, each live
    LiteLLM response and the cost of each call."""

    def __init__(self) -> None:
        super().__init__()
        self.bodies: list[Any] = []
        self.kwargs: list[dict[str, Any]] = []
        self.responses: list[Any] = []
        self.costs: dict[str, float] = {}
        self.chunks: list[list[Any]] = []

    def log_pre_api_call(self, model: Any, messages: Any, kwargs: Any) -> None:
        extra = kwargs.get("additional_args") or {}
        body = extra.get("complete_input_dict")
        if isinstance(body, str):
            try:
                body = json.loads(body)
            except ValueError:
                pass
        self.bodies.append(to_jsonable(body))

    def _record_cost(self, kwargs: Any, response_obj: Any) -> None:
        call_id = str(kwargs.get("litellm_call_id"))
        cost = kwargs.get("response_cost")
        if not cost:
            usage = getattr(response_obj, "usage", None)
            cost = getattr(usage, "cost", None) if usage is not None else None
        self.costs[call_id] = float(cost or 0.0)

    def log_success_event(
        self, kwargs: Any, response_obj: Any, start_time: Any, end_time: Any
    ) -> None:
        self._record_cost(kwargs, response_obj)

    async def async_log_success_event(
        self, kwargs: Any, response_obj: Any, start_time: Any, end_time: Any
    ) -> None:
        self._record_cost(kwargs, response_obj)

    def mark(self) -> tuple[int, int, int]:
        """Positions in the body, kwargs and response lists, to slice one run's share."""
        return len(self.bodies), len(self.kwargs), len(self.responses)

    def total_cost(self) -> float:
        return sum(self.costs.values())


REC = Recorder()
EXTRA_COST: list[float] = []


def install_hooks() -> None:
    warnings.filterwarnings("ignore", message="Pydantic serializer warnings")
    litellm.suppress_debug_info = True
    os.environ["KILN_SKIP_REMOTE_MODEL_LIST"] = "true"
    settings_dir = Path(tempfile.mkdtemp(prefix="kiln_pv_settings_"))
    patch.object(
        Config, "settings_path", return_value=str(settings_dir / "settings.yaml")
    ).start()
    Config._shared_instance = None
    litellm.callbacks.append(REC)

    original_build = LiteLlmAdapter.build_completion_kwargs
    original_check = LiteLlmAdapter.acompletion_checking_response
    original_validate = adapter_stream._validate_response

    async def build(self: LiteLlmAdapter, *args: Any, **kwargs: Any) -> Any:
        result = await original_build(self, *args, **kwargs)
        REC.kwargs.append(copy.deepcopy(result))
        return result

    async def check(self: LiteLlmAdapter, **kwargs: Any) -> Any:
        response, choice = await original_check(self, **kwargs)
        REC.responses.append(response)
        return response, choice

    def validate(response: Any) -> Any:
        result = original_validate(response)
        REC.responses.append(result[0])
        return result

    patch.object(LiteLlmAdapter, "build_completion_kwargs", build).start()
    patch.object(LiteLlmAdapter, "acompletion_checking_response", check).start()
    patch.object(adapter_stream, "_validate_response", validate).start()
    patch.object(adapter_stream, "StreamingCompletion", RecordingStream).start()


class RecordingStream(StreamingCompletion):
    """Kiln's StreamingCompletion, keeping each call's raw LiteLLM chunks."""

    async def __aiter__(self) -> Any:
        chunks: list[Any] = []
        REC.chunks.append(chunks)
        async for chunk in super().__aiter__():
            chunks.append(chunk)
            yield chunk


def make_task(instruction: str = INSTRUCTION) -> Task:
    root = Path(tempfile.mkdtemp(prefix="kiln_pv_project_"))
    project = Project(name="Provider verification", path=root / "project.kiln")
    project.save_to_file()
    task = Task(name="Provider verification", instruction=instruction, parent=project)
    task.save_to_file()
    return task


def make_adapter(
    task: Task,
    model: str,
    provider: ModelProviderName,
    thinking: str | None,
    *,
    return_on_tool_call: bool = False,
    caching: bool = False,
    tools: bool = True,
) -> LiteLlmAdapter:
    tools_config = (
        ToolsRunConfig(
            tools=[
                KilnBuiltInToolId.ADD_NUMBERS,
                KilnBuiltInToolId.SUBTRACT_NUMBERS,
                KilnBuiltInToolId.MULTIPLY_NUMBERS,
                KilnBuiltInToolId.DIVIDE_NUMBERS,
            ]
        )
        if tools
        else None
    )
    properties = KilnAgentRunConfigProperties(
        model_name=model,
        model_provider_name=provider,
        prompt_id=PromptGenerators.SIMPLE,
        structured_output_mode=StructuredOutputMode.unknown,
        tools_config=tools_config,
        thinking_level=thinking,
    )
    # The paid tests build LiteLlmConfig directly; Ollama also needs the base URL and
    # placeholder key that Kiln's adapter registry adds.
    config = (
        litellm_core_provider_config(properties)
        if provider == ModelProviderName.ollama
        else LiteLlmConfig(run_config_properties=properties)
    )
    return LiteLlmAdapter(
        kiln_task=task,
        config=config,
        base_adapter_config=AdapterConfig(
            return_on_tool_call=return_on_tool_call,
            automatic_prompt_caching=caching,
        ),
    )


def error_text(error: BaseException) -> str:
    text = f"{type(error).__name__}: {error}"
    cause = error.__cause__ or error.__context__
    if cause is not None and str(cause) not in text:
        text += f" | cause {type(cause).__name__}: {cause}"
    return text[:1500]


def usage_of(response: Any) -> dict[str, Any]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return {}
    dumped = to_jsonable(usage.model_dump(exclude_none=True))
    details = dumped.get("prompt_tokens_details") or {}
    completion_details = dumped.get("completion_tokens_details") or {}
    return {
        "prompt_tokens": dumped.get("prompt_tokens"),
        "cached_tokens": details.get("cached_tokens"),
        "cache_creation_input_tokens": dumped.get("cache_creation_input_tokens"),
        "cache_read_input_tokens": dumped.get("cache_read_input_tokens"),
        "completion_tokens": dumped.get("completion_tokens"),
        "reasoning_tokens": completion_details.get("reasoning_tokens"),
        "raw": dumped,
    }


def message_of(response: Any) -> Any:
    return response.choices[0].message


class KilnResult:
    def __init__(self) -> None:
        self.status = "ok"
        self.error: str | None = None
        self.run: Any = None
        self.bodies: list[Any] = []
        self.kwargs: list[dict[str, Any]] = []
        self.responses: list[Any] = []
        self.chunks: list[list[Any]] = []
        self.seconds = 0.0

    def record(self) -> dict[str, Any]:
        trace = self.run.trace if self.run is not None else None
        intermediate = self.run.intermediate_outputs if self.run is not None else None
        return {
            "status": self.status,
            "error": self.error,
            "seconds": round(self.seconds, 1),
            "output": self.run.output.output if self.run is not None else None,
            "toolcall_pending": self.run.is_toolcall_pending if self.run else None,
            "intermediate_outputs": intermediate,
            "trace": trace,
            "calls": [
                {
                    "usage": usage_of(response),
                    "message": dump_message(message_of(response)),
                }
                for response in self.responses
            ],
            "bodies": self.bodies,
        }


async def kiln_run(
    adapter: LiteLlmAdapter,
    input: Any,
    prior_trace: Any = None,
    streamed: bool = False,
) -> KilnResult:
    result = KilnResult()
    bodies_at, kwargs_at, responses_at = REC.mark()
    chunks_at = len(REC.chunks)
    start = time.monotonic()
    try:
        if streamed:
            stream = adapter.invoke_openai_stream(input=input, prior_trace=prior_trace)
            async for _ in stream:
                pass
            result.run = stream.task_run
        else:
            result.run = await adapter.invoke(input=input, prior_trace=prior_trace)
    except Exception as error:
        result.status = "error"
        result.error = error_text(error)
    await asyncio.sleep(0.5)
    result.seconds = time.monotonic() - start
    result.bodies = REC.bodies[bodies_at:]
    result.kwargs = REC.kwargs[kwargs_at:]
    result.responses = REC.responses[responses_at:]
    result.chunks = REC.chunks[chunks_at:]
    return result


async def direct(kwargs: dict[str, Any], streamed: bool = False) -> dict[str, Any]:
    """Call litellm.acompletion with full control over the messages."""
    bodies_at, _, _ = REC.mark()
    record: dict[str, Any] = {"status": "ok", "streamed": streamed}
    try:
        if streamed:
            stream = StreamingCompletion(**kwargs)
            async for _ in stream:
                pass
            response = stream.response
        else:
            response = await litellm.acompletion(**kwargs)
        if not isinstance(response, litellm.ModelResponse):
            raise RuntimeError(f"Expected a ModelResponse, got {type(response)}")
        record["usage"] = usage_of(response)
        record["message"] = dump_message(message_of(response))
        record["finish_reason"] = response.choices[0].finish_reason
    except Exception as error:
        record["status"] = "error"
        record["error"] = error_text(error)
    await asyncio.sleep(0.5)
    record["bodies"] = REC.bodies[bodies_at:]
    return record


def execute_tool(call: dict[str, Any]) -> str:
    name = call["function"]["name"]
    args = json.loads(call["function"]["arguments"] or "{}")
    a, b = float(args.get("a", 0)), float(args.get("b", 0))
    if name == "add":
        value = a + b
    elif name == "subtract":
        value = a - b
    elif name == "multiply":
        value = a * b
    elif name == "divide":
        value = a / b
    else:
        raise ValueError(f"Unknown tool: {name}")
    return str(int(value)) if value == int(value) else str(value)


def tool_calls_of(message: dict[str, Any]) -> list[dict[str, Any]]:
    return message.get("tool_calls") or []


def save(section: str, data: Any) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "section": section,
        "date": time.strftime("%Y-%m-%d %H:%M:%S"),
        "litellm_cost_usd": round(REC.total_cost() + sum(EXTRA_COST), 4),
        "data": data,
    }
    path = RAW_DIR / f"{section}.json"
    path.write_text(json.dumps(trim(to_jsonable(data)), indent=1))
    print(f"[{section}] saved {path}; section cost ${data['litellm_cost_usd']}")


def short(record: dict[str, Any]) -> str:
    calls = record.get("calls") or []
    usage = [
        (
            c["usage"].get("prompt_tokens"),
            c["usage"].get("cached_tokens"),
            c["usage"].get("reasoning_tokens"),
        )
        for c in calls
    ]
    return f"{record['status']} {record.get('error') or ''} usage={usage}"


# ---------------------------------------------------------------- Anthropic


def is_doubled(text: str) -> bool:
    half = len(text) // 2
    return len(text) > 0 and len(text) % 2 == 0 and text[:half] == text[half:]


def thinking_report(message: dict[str, Any]) -> list[dict[str, Any]]:
    blocks = message.get("thinking_blocks") or []
    return [
        {
            "type": block.get("type"),
            "chars": len(block.get("thinking") or ""),
            "doubled": is_doubled(block.get("thinking") or ""),
            "signed": bool(block.get("signature")),
        }
        for block in blocks
    ]


def undouble(message: dict[str, Any]) -> dict[str, Any]:
    fixed = copy.deepcopy(message)
    for block in fixed.get("thinking_blocks") or []:
        text = block.get("thinking") or ""
        if is_doubled(text):
            block["thinking"] = text[: len(text) // 2]
    fixed.pop("provider_specific_fields", None)
    return fixed


def drop_thinking(message: dict[str, Any]) -> dict[str, Any]:
    fixed = undouble(message)
    fixed.pop("thinking_blocks", None)
    fixed.pop("reasoning_content", None)
    return fixed


def tamper_thinking(message: dict[str, Any]) -> dict[str, Any]:
    fixed = undouble(message)
    for block in fixed.get("thinking_blocks") or []:
        if block.get("thinking"):
            block["thinking"] = "I will work through the numbers one step at a time."
    return fixed


def replace_live_messages(
    messages: list[Any], transform: Any = None
) -> list[dict[str, Any]]:
    """Turn every LiteLLM Message into its saved-dict form, optionally transformed."""
    out: list[dict[str, Any]] = []
    for message in messages:
        if isinstance(message, dict):
            out.append(copy.deepcopy(message))
        else:
            dumped = dump_message(message)
            out.append(transform(dumped) if transform else dumped)
    return out


def body_assistant_blocks(body: Any) -> list[list[dict[str, Any]]]:
    """For an Anthropic body, the content block types and thinking sizes of each assistant turn."""
    turns: list[list[dict[str, Any]]] = []
    for message in (body or {}).get("messages", []):
        if message.get("role") != "assistant":
            continue
        content = message.get("content")
        if isinstance(content, str):
            turns.append([{"type": "text"}])
            continue
        turns.append(
            [
                {
                    "type": part.get("type"),
                    "chars": len(part.get("thinking") or part.get("text") or ""),
                    "doubled": is_doubled(part.get("thinking") or ""),
                }
                for part in content
            ]
        )
    return turns


async def q1() -> None:
    task = make_task()
    runs = []
    for rep in range(1):
        adapter = make_adapter(
            task, "claude_sonnet_5_5", ModelProviderName.anthropic, "high"
        )
        result = await kiln_run(adapter, PROMPT, streamed=True)
        record = result.record()
        record["live_thinking"] = [
            thinking_report(dump_message(message_of(r))) for r in result.responses
        ]
        record["body_assistant_blocks"] = [
            body_assistant_blocks(b) for b in result.bodies
        ]
        print(f"q1 rep {rep} streamed loop: {short(record)}")
        print("  live thinking:", record["live_thinking"])
        print("  body blocks:", record["body_assistant_blocks"])

        comparisons = []
        for round_index, kwargs in enumerate(result.kwargs):
            if round_index == 0:
                continue
            for variant, transform in (
                ("as_sent_dict", None),
                ("corrected", undouble),
                ("no_thinking", drop_thinking),
                ("tampered_text_same_signature", tamper_thinking),
            ):
                replay = dict(kwargs)
                replay["messages"] = replace_live_messages(
                    kwargs["messages"], transform
                )
                outcome = await direct(replay, streamed=False)
                outcome["round"] = round_index + 1
                outcome["variant"] = variant
                outcome["body_assistant_blocks"] = [
                    body_assistant_blocks(b) for b in outcome["bodies"]
                ]
                comparisons.append(outcome)
                print(
                    f"  replay round {round_index + 1} {variant}: {outcome['status']} "
                    f"{outcome.get('error') or ''} prompt={outcome.get('usage', {}).get('prompt_tokens')}"
                )
            break
        record["replays"] = comparisons
        runs.append(record)
    save("q1_anthropic_doubled_thinking", runs)


async def resume_chain(
    task: Task,
    model: str,
    thinking: str,
    case: str,
    provider: ModelProviderName = ModelProviderName.anthropic,
    streamed: bool = False,
    native_key: str = "thinking_blocks",
    native_from: Any = None,
    max_steps: int = 12,
) -> dict[str, Any]:
    """Run with return_on_tool_call, then resume from the saved trace until done.
    Case "a" resumes from the trace as Kiln saves it today. Case "b" first adds the
    native reasoning of the newest assistant message to the trace."""
    adapter = make_adapter(task, model, provider, thinking, return_on_tool_call=True)
    steps: list[dict[str, Any]] = []
    native_by_call: dict[str, Any] = {}
    result = await kiln_run(adapter, PROMPT, streamed=streamed)
    steps.append(result.record())
    print(f"  {model} case {case} step 1: {short(steps[-1])}")
    while (
        result.run is not None
        and result.run.is_toolcall_pending
        and len(steps) < max_steps
    ):
        trace = copy.deepcopy(result.run.trace)
        if case == "b" and result.responses:
            live = dump_message(message_of(result.responses[-1]))
            native = native_from(live) if native_from else live.get(native_key)
            calls = tool_calls_of(trace[-1])
            if native and calls:
                native_by_call[calls[0]["id"]] = native
            # Kiln's TaskRun validation drops unknown trace keys, so every earlier
            # assistant message needs its native reasoning added back each time.
            for message in trace:
                calls = (
                    tool_calls_of(message) if message.get("role") == "assistant" else []
                )
                if calls and calls[0]["id"] in native_by_call:
                    message[native_key] = native_by_call[calls[0]["id"]]
        tool_results = [
            {"tool_call_id": call["id"], "content": execute_tool(call)}
            for call in tool_calls_of(trace[-1])
        ]
        result = await kiln_run(
            adapter, tool_results, prior_trace=trace, streamed=streamed
        )
        step = result.record()
        step["sent_prior_trace_last_assistant"] = trace[-1]
        steps.append(step)
        print(f"  {model} case {case} step {len(steps)}: {short(step)}")
    final = steps[-1]
    return {
        "model": model,
        "thinking": thinking,
        "case": case,
        "streamed": streamed,
        "provider": provider.value,
        "final_correct": bool(final.get("output") and ANSWER in final["output"]),
        "steps": steps,
    }


def anthropic_resume_summary(chain: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for index, step in enumerate(chain["steps"]):
        body = step["bodies"][0] if step["bodies"] else {}
        calls = step["calls"]
        message = calls[0]["message"] if calls else {}
        rows.append(
            {
                "step": index + 1,
                "status": step["status"],
                "error": step["error"],
                "thinking_param": body.get("thinking"),
                "body_assistant_blocks": body_assistant_blocks(body),
                "response_thinking": thinking_report(message),
                "response_has_reasoning_content": bool(
                    message.get("reasoning_content")
                ),
                "usage": calls[0]["usage"] if calls else None,
            }
        )
    return rows


async def q2(cases: tuple[tuple[str, str, str], ...] | None = None) -> None:
    task = make_task()
    chains = []
    for model, thinking, case in cases or (
        ("claude_sonnet_5_5", "high", "a"),
        ("claude_sonnet_5_5", "high", "b"),
        ("claude_opus_4_5", "high", "a"),
        ("claude_opus_4_5", "high", "b"),
    ):
        chain = await resume_chain(task, model, thinking, case)
        chain["summary"] = anthropic_resume_summary(chain)
        for row in chain["summary"]:
            turns = row["body_assistant_blocks"]
            print(
                f"    step {row['step']} {row['status']} {row['error'] or ''} "
                f"thinking-in-body={[sum(b['type'] == 'thinking' for b in t) for t in turns]} "
                f"response-thinking={len(row['response_thinking'])} "
                f"prompt={(row['usage'] or {}).get('prompt_tokens')}"
            )
        print("    final correct:", chain["final_correct"])
        chains.append(chain)
    save("q2_anthropic_resume" + ("_b_fixed" if cases else ""), chains)


async def q2b() -> None:
    await q2(
        (
            ("claude_sonnet_5_5", "high", "b"),
            ("claude_opus_4_5", "high", "b"),
        )
    )


# ---------------------------------------------------------------- OpenRouter

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def reasoning_details_of(message: dict[str, Any]) -> Any:
    psf = message.get("provider_specific_fields") or {}
    return message.get("reasoning_details") or psf.get("reasoning_details")


def streamed_details(chunks: list[Any]) -> list[dict[str, Any]]:
    """Every delta.reasoning_details fragment of one streamed LiteLLM call, in order."""
    fragments: list[dict[str, Any]] = []
    for chunk in chunks:
        for choice in chunk.choices:
            delta = choice.delta
            found = getattr(delta, "reasoning_details", None)
            if not found:
                psf = getattr(delta, "provider_specific_fields", None) or {}
                found = psf.get("reasoning_details")
            fragments.extend(to_jsonable(found or []))
    return fragments


def merge_details(fragments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge fragments that share type and index: text, summary and data are
    concatenated; id, format and signature keep the first non-empty value."""
    merged: list[dict[str, Any]] = []
    for fragment in fragments:
        last = merged[-1] if merged else None
        if (
            last is not None
            and last.get("type") == fragment.get("type")
            and last.get("index") == fragment.get("index")
        ):
            for key, value in fragment.items():
                if key in ("text", "summary", "data") and isinstance(value, str):
                    last[key] = (last.get(key) or "") + value
                elif value not in (None, "") and last.get(key) in (None, ""):
                    last[key] = value
        else:
            merged.append(copy.deepcopy(fragment))
    return merged


def describe_details(details: Any) -> list[dict[str, Any]]:
    out = []
    for item in details or []:
        out.append(
            {
                "type": item.get("type"),
                "index": item.get("index"),
                "id": (item.get("id") or "")[:24] or None,
                "format": item.get("format"),
                "text_chars": len(item.get("text") or ""),
                "summary_chars": len(item.get("summary") or ""),
                "data_chars": len(item.get("data") or ""),
                "signature_chars": len(item.get("signature") or ""),
            }
        )
    return out


def openrouter_variant(message: dict[str, Any], variant: str) -> dict[str, Any]:
    out = copy.deepcopy(message)
    details = reasoning_details_of(out)
    if variant == "no_reasoning":
        for key in (
            "provider_specific_fields",
            "reasoning_content",
            "reasoning_details",
        ):
            out.pop(key, None)
    elif variant == "plus_details" and details:
        out["reasoning_details"] = details
    elif variant == "planned" and details:
        out["reasoning_details"] = details
        out.pop("provider_specific_fields", None)
        out.pop("reasoning_content", None)
    return out


def add_native_to_trace(
    trace: list[dict[str, Any]], lives: list[dict[str, Any]], variant: str
) -> list[dict[str, Any]]:
    """Give each assistant message of a fresh run's trace the reasoning_details of
    the live response it came from, in order."""
    out = copy.deepcopy(trace)
    assistants = [m for m in out if m.get("role") == "assistant"]
    for message, live in zip(assistants, lives):
        details = reasoning_details_of(live)
        if details:
            message["reasoning_details"] = details
            if variant == "planned":
                message.pop("reasoning_content", None)
    return out


async def round_two_replays(
    result: KilnResult, variants: tuple[str, ...]
) -> list[dict[str, Any]]:
    """Send the run's second request again, non-streamed, with each variant of the
    earlier assistant messages."""
    outcomes = []
    if len(result.kwargs) < 2:
        return outcomes
    kwargs = result.kwargs[1]
    for variant in variants:
        replay = dict(kwargs)
        replay["messages"] = [
            openrouter_variant(m, variant) if m.get("role") == "assistant" else m
            for m in replace_live_messages(kwargs["messages"])
        ]
        outcome = await direct(replay)
        outcome["variant"] = variant
        outcomes.append(outcome)
        print(
            f"    round-2 replay {variant}: {outcome['status']} {outcome.get('error') or ''} "
            f"prompt={outcome.get('usage', {}).get('prompt_tokens')} "
            f"cached={outcome.get('usage', {}).get('cached_tokens')}"
        )
    return outcomes


async def openrouter_suite(model: str, thinking: str | None) -> dict[str, Any]:
    task = make_task()
    provider = ModelProviderName.openrouter
    out: dict[str, Any] = {"model": model, "thinking": thinking}
    lives_of = lambda r: [dump_message(message_of(x)) for x in r.responses]  # noqa: E731

    adapter = make_adapter(task, model, provider, thinking)
    loop = await kiln_run(adapter, PROMPT)
    out["loop_non_streamed"] = loop.record()
    print(f"  {model}/{thinking} loop non-streamed: {short(out['loop_non_streamed'])}")
    out["loop_non_streamed"]["live_details"] = [
        describe_details(reasoning_details_of(m)) for m in lives_of(loop)
    ]
    out["round_two_replays"] = await round_two_replays(
        loop, ("as_sent", "no_reasoning", "plus_details", "planned")
    )

    adapter = make_adapter(task, model, provider, thinking)
    streamed = await kiln_run(adapter, PROMPT, streamed=True)
    out["loop_streamed"] = streamed.record()
    out["loop_streamed"]["streamed_details"] = [
        describe_details(streamed_details(c)) for c in streamed.chunks
    ]
    print(f"  {model}/{thinking} loop streamed: {short(out['loop_streamed'])}")
    if streamed.status != "ok" and len(streamed.kwargs) >= 2 and streamed.chunks:
        retries = []
        for label, details in (
            ("streamed_as_is", streamed_details(streamed.chunks[0])),
            ("streamed_merged", merge_details(streamed_details(streamed.chunks[0]))),
        ):
            replay = dict(streamed.kwargs[1])
            messages = replace_live_messages(streamed.kwargs[1]["messages"])
            first = next(m for m in messages if m.get("role") == "assistant")
            first["reasoning_details"] = details
            replay["messages"] = messages
            outcome = await direct(replay)
            outcome["variant"] = label
            retries.append(outcome)
            print(
                f"    streamed retry {label}: {outcome['status']} {outcome.get('error') or ''}"
            )
        out["loop_streamed_retries"] = retries

    chain = await resume_chain(task, model, thinking or "", "a", provider=provider)
    out["resume_a"] = chain
    failed = any(s["status"] != "ok" for s in chain["steps"])
    if failed:
        out["resume_b"] = await resume_chain(
            task,
            model,
            thinking or "",
            "b",
            provider=provider,
            native_key="reasoning_details",
            native_from=reasoning_details_of,
        )

    if loop.status == "ok" and loop.run is not None:
        adapter = make_adapter(task, model, provider, thinking)
        cont = await kiln_run(adapter, FOLLOW_UP, prior_trace=loop.run.trace)
        out["continuation"] = cont.record()
        print(f"  {model}/{thinking} continuation: {short(out['continuation'])}")
        for variant in ("plus_details", "planned"):
            trace = add_native_to_trace(loop.run.trace, lives_of(loop), variant)
            adapter = make_adapter(task, model, provider, thinking)
            again = await kiln_run(adapter, FOLLOW_UP, prior_trace=trace)
            out[f"continuation_{variant}"] = again.record()
            print(
                f"  {model}/{thinking} continuation {variant}: {short(out[f'continuation_{variant}'])}"
            )
    return out


async def q3() -> None:
    results = []
    for thinking in ("low", "high"):
        results.append(await openrouter_suite("gemini_4_argon", thinking))
    save("q3_openrouter_gemini", results)


async def q4() -> None:
    results = []
    for thinking in ("medium", "low"):
        results.append(await openrouter_suite("claude_sonnet_5_5", thinking))
    save("q4_openrouter_claude", results)


def parse_sse(lines: list[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Raw OpenRouter SSE lines to chunk dicts, plus the assistant message they build
    (content, tool calls by index, and the reasoning_details fragments in order)."""
    chunks: list[dict[str, Any]] = []
    message: dict[str, Any] = {"role": "assistant", "content": "", "fragments": []}
    calls: dict[int, dict[str, Any]] = {}
    for line in lines:
        if not line.startswith("data: ") or line.strip() == "data: [DONE]":
            continue
        chunk = json.loads(line[len("data: ") :])
        chunks.append(chunk)
        for choice in chunk.get("choices") or []:
            delta = choice.get("delta") or {}
            message["content"] += delta.get("content") or ""
            message["fragments"].extend(delta.get("reasoning_details") or [])
            for call in delta.get("tool_calls") or []:
                slot = calls.setdefault(
                    call.get("index", 0),
                    {
                        "id": None,
                        "type": "function",
                        "function": {"name": "", "arguments": ""},
                    },
                )
                slot["id"] = slot["id"] or call.get("id")
                function = call.get("function") or {}
                slot["function"]["name"] += function.get("name") or ""
                slot["function"]["arguments"] += function.get("arguments") or ""
    message["tool_calls"] = [calls[i] for i in sorted(calls)]
    return chunks, message


async def raw_openrouter(body: dict[str, Any], stream: bool) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"}
    request = dict(body, stream=stream)
    async with httpx.AsyncClient(timeout=300) as client:
        if not stream:
            response = await client.post(OPENROUTER_URL, json=request, headers=headers)
            data = response.json()
            EXTRA_COST.append(float((data.get("usage") or {}).get("cost") or 0))
            return {"http_status": response.status_code, "json": data}
        lines: list[str] = []
        async with client.stream(
            "POST", OPENROUTER_URL, json=request, headers=headers
        ) as response:
            async for line in response.aiter_lines():
                lines.append(line)
            status = response.status_code
    chunks, message = parse_sse(lines)
    for chunk in chunks:
        if chunk.get("usage"):
            EXTRA_COST.append(float(chunk["usage"].get("cost") or 0))
    if status != 200:
        return {"http_status": status, "lines": lines[:20]}
    return {"http_status": status, "chunks": chunks, "message": message}


def raw_usage(data: dict[str, Any]) -> dict[str, Any]:
    usage = data.get("usage") or {}
    return {
        "prompt_tokens": usage.get("prompt_tokens"),
        "cached_tokens": (usage.get("prompt_tokens_details") or {}).get(
            "cached_tokens"
        ),
        "reasoning_tokens": (usage.get("completion_tokens_details") or {}).get(
            "reasoning_tokens"
        ),
        "cost": usage.get("cost"),
    }


async def q5() -> None:
    task = make_task()
    results = []
    for model, slug, reasoning in (
        ("gemini_4_argon", "google/gemini-4-argon", {"enabled": True}),
        ("claude_sonnet_5_5", "anthropic/claude-sonnet-5.5", {"effort": "medium"}),
        ("gpt_6_luna", "openai/gpt-6-luna", {"effort": "medium"}),
    ):
        adapter = make_adapter(task, model, ModelProviderName.openrouter, "medium")
        tools = await adapter.litellm_tools()
        messages = [
            {"role": "system", "content": INSTRUCTION},
            {"role": "user", "content": PROMPT},
        ]
        body: dict[str, Any] = {
            "model": slug,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "reasoning": reasoning,
            "usage": {"include": True},
        }
        record: dict[str, Any] = {"model": model, "slug": slug, "request": body}
        non_streamed = await raw_openrouter(body, stream=False)
        record["non_streamed"] = non_streamed
        ns_message = ((non_streamed.get("json") or {}).get("choices") or [{}])[0].get(
            "message"
        ) or {}
        record["non_streamed_details"] = describe_details(
            ns_message.get("reasoning_details")
        )
        streamed = await raw_openrouter(body, stream=True)
        record["streamed"] = streamed
        fragments = (streamed.get("message") or {}).get("fragments") or []
        record["streamed_fragments"] = describe_details(fragments)
        record["streamed_merged"] = describe_details(merge_details(fragments))
        print(f"== {model}: non-streamed items {record['non_streamed_details']}")
        print(
            f"   streamed fragments ({len(fragments)}): {record['streamed_fragments'][:12]}"
        )
        print(f"   merged: {record['streamed_merged']}")

        replays = []
        message = streamed.get("message") or {}
        if message.get("tool_calls"):
            tool_messages = [
                {"role": "tool", "tool_call_id": c["id"], "content": execute_tool(c)}
                for c in message["tool_calls"]
            ]
            for label, details in (
                ("as_is", fragments),
                ("merged", merge_details(fragments)),
                ("none", None),
            ):
                assistant: dict[str, Any] = {
                    "role": "assistant",
                    "content": message.get("content") or None,
                    "tool_calls": message["tool_calls"],
                }
                if details:
                    assistant["reasoning_details"] = details
                replay_body = dict(
                    body, messages=[*messages, assistant, *tool_messages]
                )
                outcome = await raw_openrouter(replay_body, stream=False)
                data = outcome.get("json") or {}
                replays.append(
                    {
                        "variant": label,
                        "http_status": outcome["http_status"],
                        "error": data.get("error"),
                        "usage": raw_usage(data),
                    }
                )
                print(f"   replay {label}: {replays[-1]}")
        record["replays"] = replays
        results.append(record)
    save("q5_openrouter_streamed_details", results)


async def q5b() -> None:
    """Claude on OpenRouter: why streamed reasoning_details were not counted."""
    task = make_task()
    adapter = make_adapter(
        task, "claude_sonnet_5_5", ModelProviderName.openrouter, "medium"
    )
    tools = await adapter.litellm_tools()
    messages = [
        {"role": "system", "content": INSTRUCTION},
        {"role": "user", "content": PROMPT},
    ]
    body: dict[str, Any] = {
        "model": "anthropic/claude-sonnet-5.5",
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
        "reasoning": {"effort": "medium"},
        "usage": {"include": True},
    }
    rows: list[dict[str, Any]] = []

    async def replay(label: str, assistant: dict[str, Any], calls: list[Any]) -> None:
        tool_messages = [
            {"role": "tool", "tool_call_id": c["id"], "content": execute_tool(c)}
            for c in calls
        ]
        outcome = await raw_openrouter(
            dict(body, messages=[*messages, assistant, *tool_messages]), stream=False
        )
        data = outcome.get("json") or {}
        rows.append(
            {
                "variant": label,
                "http_status": outcome["http_status"],
                "error": data.get("error"),
                "usage": raw_usage(data),
                "assistant_keys": sorted(assistant.keys()),
            }
        )
        print(f"   {label}: {rows[-1]}")

    for attempt in range(int(os.environ.get("PV_Q5B_START", "0")), 2):
        ns = await raw_openrouter(body, stream=False)
        message = (ns.get("json") or {})["choices"][0]["message"]
        calls = message.get("tool_calls") or []
        base = {
            "role": "assistant",
            "content": message.get("content"),
            "tool_calls": calls,
        }
        await replay(f"non_streamed_none_{attempt}", base, calls)
        await replay(
            f"non_streamed_details_{attempt}",
            dict(base, reasoning_details=message.get("reasoning_details")),
            calls,
        )
        st = await raw_openrouter(body, stream=True)
        smessage = st.get("message") or {}
        scalls = smessage.get("tool_calls") or []
        sbase = {
            "role": "assistant",
            "content": smessage.get("content") or None,
            "tool_calls": scalls,
        }
        merged = merge_details(smessage.get("fragments") or [])
        await replay(f"streamed_none_{attempt}", sbase, scalls)
        await replay(
            f"streamed_merged_{attempt}", dict(sbase, reasoning_details=merged), scalls
        )
        await replay(
            f"streamed_as_is_{attempt}",
            dict(sbase, reasoning_details=smessage.get("fragments")),
            scalls,
        )
        if attempt == 1:
            empty_text = [dict(item, text="") for item in merged]
            await replay(
                "streamed_merged_empty_text",
                dict(sbase, reasoning_details=empty_text),
                scalls,
            )
            unsigned = [
                {k: v for k, v in item.items() if k != "signature"} for item in merged
            ]
            await replay(
                "streamed_merged_no_signature",
                dict(sbase, reasoning_details=unsigned),
                scalls,
            )
            ns_details = message.get("reasoning_details") or []
            await replay(
                "non_streamed_details_empty_text",
                dict(base, reasoning_details=[dict(i, text="") for i in ns_details]),
                calls,
            )
        print(
            "   streamed text chars",
            len(smessage.get("content") or ""),
            "calls",
            len(scalls),
            "non-streamed text chars",
            len(message.get("content") or ""),
            "calls",
            len(calls),
        )
    save("q5b_openrouter_claude_streamed" + os.environ.get("PV_SUFFIX", ""), rows)


# ------------------------------------------------- Caching (q9) and Gemini (q6)

NATIVE_FIELDS = (
    "content",
    "tool_calls",
    "reasoning_content",
    "thinking_blocks",
    "reasoning_items",
    "provider_specific_fields",
)


def long_instruction() -> str:
    """A system prompt of roughly 4,500 tokens: the math task plus a handbook of rules
    the model never needs, so system prompt and tools clear every cache minimum."""
    rules = [
        f"Handbook rule {n}: when a customer of store number {n * 7 % 97} asks about "
        f"order batch {n * 13 % 101}, confirm the batch code, restate the delivery "
        f"window of {n % 5 + 2} days, and never promise a refund above {n * 3} dollars."
        for n in range(1, 131)
    ]
    return (
        INSTRUCTION
        + "\n\nReference handbook (not needed for math):\n"
        + "\n".join(rules)
    )


def restore_native(
    trace: list[dict[str, Any]],
    lives: list[dict[str, Any]],
    drop: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    """Replace each assistant message of a fresh run's trace with the JSON round-trip
    of the live message it came from, keeping only the fields LiteLLM sends."""
    out = []
    remaining = iter(lives)
    for message in trace:
        if message.get("role") != "assistant":
            out.append(copy.deepcopy(message))
            continue
        live = next(remaining)
        restored: dict[str, Any] = {"role": "assistant"}
        for key in NATIVE_FIELDS:
            if key in live and key not in drop:
                restored[key] = copy.deepcopy(live[key])
        out.append(restored)
    return out


def cache_row(
    label: str, result: KilnResult, turn_one_input: int | None
) -> dict[str, Any]:
    record = result.record()
    usage = record["calls"][0]["usage"] if record["calls"] else {}
    cached = usage.get("cached_tokens") or usage.get("cache_read_input_tokens") or 0
    share = cached / turn_one_input if turn_one_input else None
    row = {
        "label": label,
        "status": record["status"],
        "error": record["error"],
        "prompt_tokens": usage.get("prompt_tokens"),
        "cached_tokens": cached,
        "cache_creation_input_tokens": usage.get("cache_creation_input_tokens"),
        "reasoning_tokens": usage.get("reasoning_tokens"),
        "share_of_turn_one_last_input": round(share, 4) if share is not None else None,
        "output": record["output"],
    }
    print(f"    {label}: {row}")
    return {"row": row, "record": record}


async def cache_suite(
    model: str,
    provider: ModelProviderName,
    thinking: str,
    caching: bool,
    streamed: bool,
    extra_variants: tuple[tuple[str, tuple[str, ...]], ...] = (),
) -> dict[str, Any]:
    task = make_task(long_instruction())
    adapter = make_adapter(task, model, provider, thinking, caching=caching)
    first = await kiln_run(adapter, PROMPT, streamed=streamed)
    turn_one = first.record()
    print(f"  {model}/{provider.value} streamed={streamed} turn 1: {short(turn_one)}")
    out: dict[str, Any] = {
        "model": model,
        "provider": provider.value,
        "thinking": thinking,
        "caching_markers": caching,
        "streamed": streamed,
        "turn_one": turn_one,
    }
    if first.run is None or first.status != "ok":
        return out
    last_usage = turn_one["calls"][-1]["usage"]
    turn_one_input = last_usage.get("prompt_tokens")
    out["turn_one_last_request_input"] = turn_one_input
    lives = [dump_message(message_of(r)) for r in first.responses]
    variants: list[tuple[str, list[dict[str, Any]]]] = [
        ("restored", restore_native(first.run.trace, lives)),
        ("restored_repeat", restore_native(first.run.trace, lives)),
    ]
    for label, drop in extra_variants:
        variants.append((label, restore_native(first.run.trace, lives, drop)))
    variants.append(("today_saved_trace", copy.deepcopy(first.run.trace)))
    rows = []
    for label, trace in variants:
        await asyncio.sleep(5)
        second = make_adapter(task, model, provider, thinking, caching=caching)
        result = await kiln_run(second, FOLLOW_UP, prior_trace=trace, streamed=streamed)
        rows.append(cache_row(label, result, turn_one_input))
    out["turn_two"] = rows
    return out


async def q9() -> None:
    results = [
        await cache_suite(
            "claude_sonnet_5_5", ModelProviderName.anthropic, "high", True, False
        ),
        await cache_suite(
            "claude_sonnet_5_5", ModelProviderName.anthropic, "high", True, True
        ),
    ]
    save("q9_anthropic_caching", results)


async def q6() -> None:
    results = [
        await cache_suite(
            "gemini_4_argon",
            ModelProviderName.gemini_api,
            "high",
            False,
            False,
            extra_variants=(
                (
                    "restored_without_reasoning_content",
                    ("reasoning_content", "thinking_blocks"),
                ),
                ("restored_without_signatures", ("provider_specific_fields",)),
            ),
        ),
    ]
    save("q6_q9_gemini", results)


async def q6s() -> None:
    results = [
        await cache_suite(
            "gemini_4_argon",
            ModelProviderName.gemini_api,
            "high",
            False,
            True,
            extra_variants=(
                (
                    "restored_without_reasoning_content",
                    ("reasoning_content", "thinking_blocks"),
                ),
            ),
        ),
    ]
    save("q6_q9_gemini_streamed", results)


# ---------------------------------------------------------------- Groq (q7)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


def reasoning_text(message: dict[str, Any]) -> str | None:
    psf = message.get("provider_specific_fields") or {}
    return (
        message.get("reasoning")
        or message.get("reasoning_content")
        or psf.get("reasoning")
    )


def field_variant(message: dict[str, Any], variant: str, text: str) -> dict[str, Any]:
    out = {
        "role": "assistant",
        "content": message.get("content"),
        "tool_calls": message.get("tool_calls"),
    }
    if variant in ("reasoning", "both"):
        out["reasoning"] = text
    if variant in ("reasoning_content", "both"):
        out["reasoning_content"] = text
    return {k: v for k, v in out.items() if v is not None}


async def input_field_replays(
    result: KilnResult, variants: tuple[str, ...], label: str
) -> list[dict[str, Any]]:
    """Replay the run's second request with the first assistant message carrying its
    reasoning under each field name, and compare input tokens."""
    rows: list[dict[str, Any]] = []
    if len(result.kwargs) < 2 or not result.responses:
        return rows
    live = dump_message(message_of(result.responses[0]))
    text = reasoning_text(live)
    if not text:
        print(f"    {label}: no reasoning text on the first reply")
        return rows
    kwargs = result.kwargs[1]
    messages = replace_live_messages(kwargs["messages"])
    position = next(i for i, m in enumerate(messages) if m.get("role") == "assistant")
    for variant in variants:
        replay = dict(kwargs)
        replay_messages = copy.deepcopy(messages)
        replay_messages[position] = field_variant(messages[position], variant, text)
        replay["messages"] = replay_messages
        outcome = await direct(replay)
        outcome["variant"] = variant
        outcome["reasoning_chars"] = len(text)
        sent = outcome["bodies"][0]["messages"][position] if outcome["bodies"] else {}
        outcome["sent_assistant_keys"] = sorted(sent.keys())
        rows.append(outcome)
        print(
            f"    {label} {variant}: {outcome['status']} {outcome.get('error') or ''} "
            f"prompt={outcome.get('usage', {}).get('prompt_tokens')} keys={outcome['sent_assistant_keys']}"
        )
    return rows


async def q7() -> None:
    task = make_task()
    out: dict[str, Any] = {"model": "qwen_3p8_27b"}
    for streamed in (False, True):
        adapter = make_adapter(task, "qwen_3p8_27b", ModelProviderName.groq, "medium")
        result = await kiln_run(adapter, PROMPT, streamed=streamed)
        record = result.record()
        lives = [dump_message(message_of(r)) for r in result.responses]
        record["live_reasoning"] = [
            {
                "reasoning_attr_chars": len(m.get("reasoning") or ""),
                "reasoning_content_chars": len(m.get("reasoning_content") or ""),
                "psf_reasoning_chars": len(
                    (m.get("provider_specific_fields") or {}).get("reasoning") or ""
                ),
            }
            for m in lives
        ]
        record["trace_reasoning_content_chars"] = [
            len(m.get("reasoning_content") or "")
            for m in (record["trace"] or [])
            if m.get("role") == "assistant"
        ]
        label = "streamed" if streamed else "non_streamed"
        print(f"  groq {label}: {short(record)}")
        print(f"    live: {record['live_reasoning'][:3]}")
        print(
            f"    trace reasoning_content chars: {record['trace_reasoning_content_chars']}"
        )
        print(
            "    intermediate reasoning:",
            bool((record["intermediate_outputs"] or {}).get("reasoning")),
        )
        if result.bodies:
            first = result.bodies[0]
            print(
                "    sent settings:",
                {k: v for k, v in first.items() if k not in ("messages", "tools")},
            )
        record["replays"] = await input_field_replays(
            result, ("none", "reasoning", "reasoning_content", "both"), label
        )
        out[label] = record
        if not streamed and result.bodies:
            body = dict(result.bodies[0])
            headers = {"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"}
            async with httpx.AsyncClient(timeout=120) as client:
                raw = await client.post(GROQ_URL, json=body, headers=headers)
            data = raw.json()
            message = ((data.get("choices") or [{}])[0]).get("message") or {}
            out["raw_groq_reply"] = {
                "http_status": raw.status_code,
                "message_keys": sorted(message.keys()),
                "message": message,
                "usage": data.get("usage"),
            }
            print("    raw Groq reply keys:", out["raw_groq_reply"]["message_keys"])
    save("q7_groq", out)


async def q7b() -> None:
    """Groq: a streamed answer with no tools, then a new turn from its saved trace."""
    task = make_task()
    out: dict[str, Any] = {}
    for streamed in (True, False):
        label = "streamed" if streamed else "non_streamed"
        adapter = make_adapter(
            task, "qwen_3p8_27b", ModelProviderName.groq, "medium", tools=False
        )
        first = await kiln_run(
            adapter, "What is 17 * 23? Answer in one line.", streamed=streamed
        )
        out[f"{label}_turn_one"] = first.record()
        trace = first.run.trace if first.run else []
        print(
            f"  {label} turn 1: {short(out[f'{label}_turn_one'])} trace reasoning_content chars="
            f"{[len(m.get('reasoning_content') or '') for m in trace if m.get('role') == 'assistant']}"
        )
        if first.run is None:
            continue
        follow = make_adapter(
            task, "qwen_3p8_27b", ModelProviderName.groq, "medium", tools=False
        )
        second = await kiln_run(follow, FOLLOW_UP, prior_trace=trace, streamed=streamed)
        out[f"{label}_turn_two"] = second.record()
        print(f"  {label} turn 2 from saved trace: {short(out[f'{label}_turn_two'])}")
    save("q7b_groq_continuation", out)


# ---------------------------------------------------------------- Ollama (q8)

OLLAMA_MODEL = "qwen3.5:4b"
OLLAMA_BASE = os.environ.get("OLLAMA_BASE_URL") or "http://localhost:11434"


async def ollama_native_replays(tools: list[Any]) -> dict[str, Any]:
    """The same loop through LiteLLM's native ollama_chat provider."""
    base: dict[str, Any] = {
        "model": f"ollama_chat/{OLLAMA_MODEL}",
        "api_base": OLLAMA_BASE,
        "tools": tools,
        "reasoning_effort": "medium",
        "temperature": 0,
    }
    messages: list[Any] = [
        {"role": "system", "content": INSTRUCTION},
        {"role": "user", "content": PROMPT},
    ]
    first = await direct(dict(base, messages=messages))
    out: dict[str, Any] = {"round_one": first}
    message = first.get("message") or {}
    calls = tool_calls_of(message)
    print(
        f"    ollama_chat round 1: {first['status']} {first.get('error') or ''} "
        f"reasoning chars={len(reasoning_text(message) or '')} calls={len(calls)}"
    )
    if not calls:
        return out
    tool_messages = [
        {"role": "tool", "tool_call_id": c.get("id"), "content": execute_tool(c)}
        for c in calls
    ]
    rows = []
    text = reasoning_text(message) or ""
    for variant in ("as_live_dict", "none", "reasoning_content", "thinking"):
        if variant == "as_live_dict":
            assistant = copy.deepcopy(message)
        else:
            assistant = field_variant(message, "none", text)
            if variant == "reasoning_content":
                assistant["reasoning_content"] = text
            if variant == "thinking":
                assistant["thinking"] = text
        outcome = await direct(
            dict(base, messages=[*messages, assistant, *tool_messages])
        )
        outcome["variant"] = variant
        sent = outcome["bodies"][0]["messages"][2] if outcome["bodies"] else {}
        outcome["sent_assistant_keys"] = sorted(sent.keys())
        rows.append(outcome)
        print(
            f"    ollama_chat round 2 {variant}: {outcome['status']} {outcome.get('error') or ''} "
            f"prompt={outcome.get('usage', {}).get('prompt_tokens')} keys={outcome['sent_assistant_keys']}"
        )
    out["round_two"] = rows
    return out


async def q8() -> None:
    async with httpx.AsyncClient(timeout=10) as client:
        version = (await client.get(f"{OLLAMA_BASE}/api/version")).json()
    out: dict[str, Any] = {"ollama_version": version, "model": OLLAMA_MODEL}
    print("  ollama version", version)
    task = make_task()
    adapter = make_adapter(task, OLLAMA_MODEL, ModelProviderName.ollama, None)
    loop = await kiln_run(adapter, PROMPT)
    record = loop.record()
    record["trace_reasoning_content_chars"] = [
        len(m.get("reasoning_content") or "")
        for m in (record["trace"] or [])
        if m.get("role") == "assistant"
    ]
    print(f"  kiln openai/ route loop: {short(record)}")
    print(
        f"    trace reasoning_content chars: {record['trace_reasoning_content_chars']}"
    )
    if loop.bodies:
        print(
            "    sent settings:",
            {k: v for k, v in loop.bodies[0].items() if k not in ("messages", "tools")},
        )
    record["replays"] = await input_field_replays(
        loop, ("none", "reasoning", "reasoning_content", "both"), "openai/ route"
    )
    out["kiln_openai_route"] = record
    if loop.run is not None and loop.status == "ok":
        follow = make_adapter(task, OLLAMA_MODEL, ModelProviderName.ollama, None)
        cont = await kiln_run(follow, FOLLOW_UP, prior_trace=loop.run.trace)
        out["kiln_continuation"] = cont.record()
        print(f"  kiln continuation: {short(out['kiln_continuation'])}")
    out["native_ollama_chat"] = await ollama_native_replays(
        await adapter.litellm_tools()
    )
    save("q8_ollama", out)


SECTIONS: dict[str, Any] = {
    "q1": q1,
    "q2": q2,
    "q2b": q2b,
    "q3": q3,
    "q4": q4,
    "q5": q5,
    "q5b": q5b,
    "q6": q6,
    "q6s": q6s,
    "q7": q7,
    "q7b": q7b,
    "q8": q8,
    "q9": q9,
}


def bundle() -> None:
    combined = {}
    for path in sorted(RAW_DIR.glob("*.json")):
        combined[path.stem] = json.loads(path.read_text())
    target = HERE / "raw_results.json.gz"
    with gzip.open(target, "wt") as handle:
        json.dump(combined, handle)
    print(f"wrote {target} ({target.stat().st_size} bytes)")


async def main(names: list[str]) -> None:
    install_hooks()
    for name in names:
        before = REC.total_cost() + sum(EXTRA_COST)
        await SECTIONS[name]()
        after = REC.total_cost() + sum(EXTRA_COST)
        print(f"== {name} cost ${after - before:.4f} (run total ${after:.4f})")


if __name__ == "__main__":
    if sys.argv[1:] == ["bundle"]:
        bundle()
    else:
        asyncio.run(main(sys.argv[1:]))
