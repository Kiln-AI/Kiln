"""Red-first reproduction of the "tools + thinking level" problem for OpenAI-direct
GPT-5.4+ / GPT-6 models.

OpenAI rejects ``reasoning_effort`` together with ``tools`` on
``/v1/chat/completions`` for gpt-5.4 and newer. The fix is to route those requests to
``/v1/responses``. litellm 1.87.1 already contains an auto-bridge
(``litellm.main.responses_api_bridge_check``) that does exactly that, but its model
matcher is ``"gpt-5" in model`` + ``gpt-5.<major>`` version parsing, so it does not
match ``gpt-6-astra``.

There are therefore TWO distinct failure modes, and this test detects both:

1. Hard failure: the request goes to ``/v1/chat/completions`` carrying both
   ``reasoning_effort`` and ``tools`` and OpenAI returns a 400.
2. Silent failure: litellm's ``drop_params`` strips ``reasoning_effort`` before the
   call, the request succeeds on ``/v1/chat/completions``, and the requested thinking
   level is simply ignored.

To distinguish them we record every outgoing HTTP request made during the run by
patching ``httpx.AsyncClient.send``. That is the single choke point shared by the
OpenAI python SDK (used by litellm's chat-completions path) and litellm's own
``AsyncHTTPHandler`` (used by the responses path), so it reliably records the
bridge's *inner* request, which a litellm ``CustomLogger`` callback does not always
surface.

Regression test for that routing. Every built-in provider carrying
``openai_responses_api=True`` must reach ``/v1/responses`` with the requested effort
on the wire, run a real tool loop to a correct answer, and report usage/cost back to
Kiln. ``gpt_5_2`` is the chat-completions control: it predates the restriction, so it
must keep using ``/v1/chat/completions``.
"""

import contextlib
import json
from dataclasses import dataclass, field
from typing import Any, Iterator
from unittest.mock import Mock, patch

import httpx
import pytest

from kiln_ai.adapters.adapter_registry import adapter_for_task
from kiln_ai.adapters.ml_model_list import ModelName, built_in_models
from kiln_ai.adapters.model_adapters.test_litellm_adapter_tools import build_test_task
from kiln_ai.adapters.model_adapters.test_paid_utils import (
    skip_if_missing_provider_keys,
)
from kiln_ai.adapters.model_adapters.test_thinking_level_paid import (
    reasoning_content_from_run,
)
from kiln_ai.datamodel.datamodel_enums import ModelProviderName, StructuredOutputMode
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties
from kiln_ai.tools.built_in_tools.math_tools import AddTool

# The prompt is trivial on purpose: one tool call, then a final answer. That is two
# HTTP requests to the provider, which is the minimum needed to exercise the
# tool-result turn (the turn where a responses-API call must echo back reasoning
# items).
TOOL_PROMPT = "what is 2+2"

# Thinking level used for every case. "high" is the highest-but-one level for the
# GPT-5.4 family (none/low/medium/high/xhigh) and is a valid non-default level for
# GPT-6 Astra (low/medium/high/xhigh/max), so one value keeps the cases comparable.
REQUESTED_EFFORT = "high"


@dataclass
class RecordedRequest:
    """One outgoing HTTP request to a model provider."""

    method: str
    url: str
    path: str
    body: dict[str, Any] | None

    @property
    def effort(self) -> Any:
        """The reasoning effort actually present in the wire payload, or None.

        Chat Completions carries ``reasoning_effort: "high"``.
        The Responses API carries ``reasoning: {"effort": "high"}``.
        litellm may also emit ``reasoning_effort: {"effort": ..., "summary": ...}``.
        """
        body = self.body or {}
        raw = body.get("reasoning_effort")
        if isinstance(raw, str):
            return raw
        if isinstance(raw, dict):
            return raw.get("effort")
        reasoning = body.get("reasoning")
        if isinstance(reasoning, dict):
            return reasoning.get("effort")
        return None

    @property
    def has_tools(self) -> bool:
        return bool((self.body or {}).get("tools"))

    @property
    def payload_shape(self) -> str:
        """`messages` => chat-completions shape, `input` => responses shape."""
        body = self.body or {}
        if "input" in body:
            return "input"
        if "messages" in body:
            return "messages"
        return "?"

    @property
    def reasoning_fields(self) -> dict[str, Any]:
        """Every reasoning-ish key actually on the wire, verbatim.

        Anthropic never sees `reasoning_effort`: litellm maps it to
        `thinking: {type: enabled, budget_tokens: N}`, so `effort` is None there
        even though a thinking budget was sent. Recording the raw keys keeps the
        report honest across providers.
        """
        body = self.body or {}
        return {
            key: body[key]
            for key in ("reasoning_effort", "reasoning", "thinking")
            if key in body
        }

    def __str__(self) -> str:
        return (
            f"{self.path} (payload={self.payload_shape}, effort={self.effort!r}, "
            f"tools={self.has_tools}, reasoning_fields={self.reasoning_fields})"
        )


@dataclass
class RequestLog:
    host_fragment: str
    requests: list[RecordedRequest] = field(default_factory=list)

    @property
    def paths(self) -> list[str]:
        return [r.path for r in self.requests]

    @property
    def efforts(self) -> list[Any]:
        return [r.effort for r in self.requests]

    def summary(self) -> str:
        if not self.requests:
            return "  (no provider requests recorded)"
        return "\n".join(f"  #{i + 1} {r}" for i, r in enumerate(self.requests))


@contextlib.contextmanager
def record_provider_requests(host_fragment: str) -> Iterator[RequestLog]:
    """Record every outgoing request whose host contains ``host_fragment``.

    Patching ``httpx.AsyncClient.send`` catches both the OpenAI SDK path and
    litellm's own http handler, so the bridge's inner /v1/responses call is
    recorded even though it is issued by a different client than the outer
    ``litellm.acompletion`` call.
    """
    log = RequestLog(host_fragment=host_fragment)
    original_send = httpx.AsyncClient.send

    async def spy_send(self, *args, **kwargs):
        request = args[0] if args else kwargs.get("request")
        try:
            host = request.url.host or ""
            if host_fragment in host:
                try:
                    body = json.loads(request.content.decode("utf-8"))
                except Exception:
                    body = None
                log.requests.append(
                    RecordedRequest(
                        method=request.method,
                        url=str(request.url),
                        path=request.url.path,
                        body=body if isinstance(body, dict) else None,
                    )
                )
        except Exception:
            # Recording must never change the behaviour under test.
            pass
        return await original_send(self, *args, **kwargs)

    with patch.object(httpx.AsyncClient, "send", spy_send):
        yield log


def provider_thinking_levels(model_name: str, provider_name: str) -> list[str]:
    for model in built_in_models:
        if model.name != model_name:
            continue
        for provider in model.providers:
            if provider.name != provider_name:
                continue
            return list((provider.available_thinking_levels or {}).values())
    raise RuntimeError(f"No model {model_name} on provider {provider_name}")


def effort_for(model_name: str, provider_name: str) -> str:
    levels = provider_thinking_levels(model_name, provider_name)
    if not levels:
        raise RuntimeError(f"{model_name}/{provider_name} has no thinking levels")
    if REQUESTED_EFFORT in levels:
        return REQUESTED_EFFORT
    # Highest-but-one, as a fallback for any model without a "high" level.
    return levels[-2] if len(levels) > 1 else levels[-1]


async def run_tool_loop(
    tmp_path,
    model_name: str,
    provider_name: str,
    thinking_level: str,
    host_fragment: str,
    temperature: float = 1.0,
    top_p: float = 1.0,
):
    """Run the real Kiln adapter tool loop, recording every provider request.

    Returns (run, error, add_spy, request_log). Exactly one of run/error is set.
    """
    task = build_test_task(tmp_path)
    adapter = adapter_for_task(
        task,
        KilnAgentRunConfigProperties(
            structured_output_mode=StructuredOutputMode.json_schema,
            model_name=model_name,
            model_provider_name=ModelProviderName(provider_name),
            prompt_id="simple_prompt_builder",
            thinking_level=thinking_level,
            temperature=temperature,
            top_p=top_p,
        ),
    )

    add_spy = Mock(wraps=AddTool())

    run = None
    error: Exception | None = None
    with record_provider_requests(host_fragment) as request_log:
        with patch.object(adapter, "available_tools", return_value=[add_spy]):
            try:
                run = await adapter.invoke(TOOL_PROMPT)
            except Exception as e:
                error = e

    return run, error, add_spy, request_log


def first_error_line(error: Exception | None) -> str:
    """First line of the deepest cause.

    Kiln wraps adapter failures in KilnRunError("An unexpected error occurred."),
    which hides the provider's 400 body. Unwrap `.original` / `__cause__` so the
    verbatim provider error is what gets reported.
    """
    if error is None:
        return "(none)"
    chain: list[str] = []
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        chain.append(f"{type(current).__name__}: {current}".splitlines()[0])
        current = getattr(current, "original", None) or current.__cause__
    # The last link is the root cause (the provider error); show it first.
    return " <- ".join(reversed(chain))[:900]


def build_context(
    model_name: str,
    provider_name: str,
    thinking_level: str,
    request_log: RequestLog,
    error: Exception | None,
    run,
    tool_called: bool,
) -> str:
    reasoning = reasoning_content_from_run(run) if run is not None else None
    final_answer = repr(run.output.output[:200]) if run is not None else "None"
    return (
        f"\ncase: model={model_name} provider={provider_name} "
        f"requested_effort={thinking_level!r}"
        f"\nrequests observed ({len(request_log.requests)}):\n{request_log.summary()}"
        f"\nendpoints: {request_log.paths}"
        f"\nefforts on the wire: {request_log.efforts}"
        f"\ntool called: {tool_called}"
        f"\nfinal answer: {final_answer}"
        f"\nreasoning surfaced: "
        f"{'yes (%d chars)' % len(reasoning) if reasoning else 'no'}"
        f"\nfirst error line: {first_error_line(error)}\n"
    )


def responses_api_cases() -> list[Any]:
    """Every built-in (model, provider) pair Kiln routes through /v1/responses."""
    cases: list[Any] = []
    for model in built_in_models:
        for provider in model.providers:
            if not provider.openai_responses_api:
                continue
            cases.append(
                pytest.param(
                    model.name,
                    provider.name,
                    True,
                    id=f"{model.name}_{provider.name.value}",
                )
            )
    return cases


# gpt_5_2 is the control: it predates the 5.4 restriction, so reasoning_effort +
# tools is legal on /v1/chat/completions and no bridging should happen.
OPENAI_CASES = [
    *responses_api_cases(),
    pytest.param(
        ModelName.gpt_5_2.value,
        ModelProviderName.openai,
        False,
        id="gpt_5_2_chat_completions_control",
    ),
]


@pytest.mark.paid
@pytest.mark.parametrize(
    ("model_name", "provider_name", "expect_responses_endpoint"), OPENAI_CASES
)
async def test_openai_tools_with_thinking_level_routing(
    tmp_path, model_name: str, provider_name: str, expect_responses_endpoint: bool
):
    """Tools + an explicit thinking level must work on the OpenAI-direct provider."""
    skip_if_missing_provider_keys(provider_name)

    thinking_level = effort_for(model_name, provider_name)

    run, error, add_spy, request_log = await run_tool_loop(
        tmp_path,
        model_name=model_name,
        provider_name=provider_name,
        thinking_level=thinking_level,
        host_fragment="openai.com",
    )

    tool_called = add_spy.run.called
    ctx = build_context(
        model_name, provider_name, thinking_level, request_log, error, run, tool_called
    )
    print(ctx)

    expected_path_fragment = (
        "/responses" if expect_responses_endpoint else "/chat/completions"
    )

    assert request_log.requests, f"No provider request was recorded at all.{ctx}"

    # 1. Every request in the loop must hit the right endpoint. For gpt-5.4+ and
    #    GPT-6 that is /v1/responses, which is the only endpoint that accepts
    #    reasoning effort alongside tools.
    wrong_endpoint = [
        r for r in request_log.requests if expected_path_fragment not in r.path
    ]
    assert not wrong_endpoint, (
        f"Expected every request to go to {expected_path_fragment}, but "
        f"{len(wrong_endpoint)} of {len(request_log.requests)} did not. "
        f"Observed endpoints: {request_log.paths}.{ctx}"
    )

    # 2. Every request must actually carry the requested reasoning effort. litellm's
    #    drop_params silently removes it for models it does not recognise, which
    #    makes the thinking level a no-op rather than an error.
    missing_effort = [r for r in request_log.requests if r.effort != thinking_level]
    assert not missing_effort, (
        f"Expected every request to carry effort={thinking_level!r}, but observed "
        f"efforts {request_log.efforts}.{ctx}"
    )

    # 3. The run must have completed without error.
    assert error is None, f"Run raised: {first_error_line(error)}{ctx}"
    assert run is not None, f"No run produced.{ctx}"

    # 4. The tool loop must have made at least two provider calls: the turn that
    #    produced the tool call, and the turn that consumed the tool result.
    assert len(request_log.requests) >= 2, (
        f"Expected >=2 provider requests (tool call turn + tool result turn), "
        f"got {len(request_log.requests)}.{ctx}"
    )

    # 5. The tool was actually called, with the right arguments.
    assert tool_called, f"The 'add' tool was never called.{ctx}"
    add_kwargs = add_spy.run.call_args.kwargs
    assert add_kwargs.get("a") == 2 and add_kwargs.get("b") == 2, (
        f"Expected add(a=2, b=2), got {add_kwargs}.{ctx}"
    )

    # 6. The final answer is correct.
    assert "4" in run.output.output, f"Final answer missing '4'.{ctx}"

    # 7. Usage and cost survive the responses bridge. litellm reports cost in a
    #    different place for the responses path, and Kiln's usage_from_response has
    #    to find it there too or runs show as free.
    assert run.usage is not None, f"No usage recorded on the run.{ctx}"
    assert run.usage.cost is not None, f"No cost recorded on the run.{ctx}"
    assert run.usage.output_tokens, f"No output tokens recorded on the run.{ctx}"


# Proving the sampling-param drop costs real calls, so cover only gpt-6 (which litellm
# does not recognise as a reasoning model) and one gpt-5.x (which it does).
CUSTOM_SAMPLING_CASES = [
    pytest.param(ModelName.gpt_6_astra.value, id="gpt_6_astra"),
    pytest.param(ModelName.gpt_5_4.value, id="gpt_5_4"),
]


@pytest.mark.paid
@pytest.mark.parametrize("model_name", CUSTOM_SAMPLING_CASES)
async def test_openai_responses_drops_custom_sampling_params(tmp_path, model_name: str):
    """A run config with custom temperature/top_p must still work once routed.

    OpenAI's reasoning models reject top_p outright and accept only the default
    temperature on /v1/responses. litellm strips both for the gpt-5.x family it
    recognises, so Kiln does the same for the models it doesn't (eg gpt-6-astra),
    which would otherwise 400 on every call.
    """
    provider_name = ModelProviderName.openai
    skip_if_missing_provider_keys(provider_name)

    thinking_level = effort_for(model_name, provider_name)

    run, error, add_spy, request_log = await run_tool_loop(
        tmp_path,
        model_name=model_name,
        provider_name=provider_name,
        thinking_level=thinking_level,
        host_fragment="openai.com",
        temperature=0.4,
        top_p=0.9,
    )

    tool_called = add_spy.run.called
    ctx = build_context(
        model_name, provider_name, thinking_level, request_log, error, run, tool_called
    )
    print(ctx)

    assert request_log.requests, f"No provider request was recorded at all.{ctx}"

    kept_sampling = [
        r
        for r in request_log.requests
        if "top_p" in (r.body or {}) or "temperature" in (r.body or {})
    ]
    assert not kept_sampling, (
        f"Expected temperature and top_p to be dropped, but {len(kept_sampling)} of "
        f"{len(request_log.requests)} requests still carried one.{ctx}"
    )

    assert error is None, f"Run raised: {first_error_line(error)}{ctx}"
    assert run is not None, f"No run produced.{ctx}"
    assert tool_called, f"The 'add' tool was never called.{ctx}"
    assert "4" in run.output.output, f"Final answer missing '4'.{ctx}"
