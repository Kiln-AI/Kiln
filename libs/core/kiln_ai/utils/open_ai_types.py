"""
Wrapper for OpenAI types to make them compatible with Pydantic.

A trace is a record of what happened, and a store of a record must never reject or
quietly rewrite what it is handed. Two substitutions serve that, both on `content`:

1. `List[T]`, not `Iterable[T]` - https://github.com/pydantic/pydantic/issues/9541
   Pydantic validates an `Iterable[T]` field into a single-use ValidatorIterator
   rather than a list. Serializing reads it, and a read empties it, so a list-valued
   content would be written to disk as `content: []` - silently, and permanently.
   `List[T]` materializes at validation time instead, which also makes the message
   deep-copyable (a ValidatorIterator cannot be pickled).

2. `ContentPart` (a plain dict), not the OpenAI SDK's content-part unions. The SDK
   unions are a closed set, and closing the set at a save boundary turns data we
   cannot parse into data we destroy - see `ContentPart` for what that cost.

Every other field matches the OpenAI SDK type of the same name, with three
exceptions:

- The Kiln-only fields in `KILN_ONLY_MESSAGE_FIELDS`, which are stripped before
  messages go to a provider.
- `reasoning_content` on the assistant message, which is deliberately *not* in that
  frozenset: it is a LiteLLM field that is sent back to the provider on the next
  call, so stripping it would drop reasoning state mid-conversation.
- `tool_calls` on the assistant message, still `List[ChatCompletionMessageToolCallParam]`
  (function calls only) while the SDK has widened to function-or-custom. Pre-existing
  and narrower than `ContentPart`; a custom tool call fails validation here.
"""

from collections.abc import Mapping, MutableMapping
from typing import (
    Annotated,
    Any,
    Dict,
    Iterable,
    List,
    Literal,
    Optional,
    TypeAlias,
    Union,
)

from openai.types.chat import (
    ChatCompletionFunctionMessageParam,
    ChatCompletionMessageToolCallParam,
)
from openai.types.chat.chat_completion_assistant_message_param import (
    Audio,
    FunctionCall,
)
from pydantic import BaseModel, BeforeValidator, TypeAdapter, WrapSerializer
from pydantic.functional_serializers import SerializerFunctionWrapHandler
from typing_extensions import Required, TypedDict

from kiln_ai.utils.usage import MessageUsage

ContentPart: TypeAlias = Dict[str, Any]
"""One part of a list-valued message `content`: a text part, an image, an audio clip,
a file, a provider-specific block.

Deliberately a plain dict rather than the OpenAI SDK's part unions. Those unions are a
closed set, and every provider extends it: Kiln's own `encode_file_litellm_format`
emits `video_url` blocks and `input_audio` blocks whose `format` is `ogg`, neither of
which the SDK union admits, and LiteLLM's `format` hint on an image and Anthropic's
`cache_control` are extra keys inside parts the SDK does admit. Validating against the
closed set rejects the first pair outright - failing the save of a run the model has
already been paid for, and making any stored run holding one permanently unloadable -
and silently strips the second pair. A part is stored exactly as it was handed over.
"""


class ChatCompletionDeveloperMessageParamWrapper(TypedDict, total=False):
    """A developer message in a trace.

    Almost an exact copy of the OpenAI SDK's ChatCompletionDeveloperMessageParam;
    only the type of `content` differs. See this module's docstring for why.
    """

    content: Required[Union[str, List[ContentPart]]]
    """The contents of the developer message."""

    role: Required[Literal["developer"]]
    """The role of the messages author, in this case `developer`."""

    name: str
    """An optional name for the participant.

    Provides the model information to differentiate between participants of the same
    role.
    """


class ChatCompletionSystemMessageParamWrapper(TypedDict, total=False):
    """A system message in a trace.

    Almost an exact copy of the OpenAI SDK's ChatCompletionSystemMessageParam;
    only the type of `content` differs. See this module's docstring for why.
    """

    content: Required[Union[str, List[ContentPart]]]
    """The contents of the system message."""

    role: Required[Literal["system"]]
    """The role of the messages author, in this case `system`."""

    name: str
    """An optional name for the participant.

    Provides the model information to differentiate between participants of the same
    role.
    """


class ChatCompletionUserMessageParamWrapper(TypedDict, total=False):
    """A user message in a trace.

    Almost an exact copy of the OpenAI SDK's ChatCompletionUserMessageParam; only
    the type of `content` differs. See this module's docstring for why.

    This is the multimodal message type: its content parts include images, audio
    and files, not only text.
    """

    content: Required[Union[str, List[ContentPart]]]
    """The contents of the user message."""

    role: Required[Literal["user"]]
    """The role of the messages author, in this case `user`."""

    name: str
    """An optional name for the participant.

    Provides the model information to differentiate between participants of the same
    role.
    """


class ChatCompletionAssistantMessageParamWrapper(TypedDict, total=False):
    """An assistant message in a trace.

    Almost a copy of the OpenAI SDK's ChatCompletionAssistantMessageParam, with the
    `content` and `tool_calls` type changes described in this module's docstring, and
    three added fields: `reasoning_content` (sent on to the provider), plus
    `latency_ms` and `usage` (Kiln-only, stripped before the message is sent).
    """

    role: Required[Literal["assistant"]]
    """The role of the messages author, in this case `assistant`."""

    audio: Optional[Audio]
    """Data about a previous audio response from the model.

    [Learn more](https://platform.openai.com/docs/guides/audio).
    """

    content: Union[str, List[ContentPart], None]
    """The contents of the assistant message.

    Required unless `tool_calls` or `function_call` is specified.
    """

    reasoning_content: Optional[str]
    """The reasoning content of the assistant message. 
    
    A LiteLLM property for reasoning data: https://docs.litellm.ai/docs/reasoning_content
    """

    function_call: Optional[FunctionCall]
    """Deprecated and replaced by `tool_calls`.

    The name and arguments of a function that should be called, as generated by the
    model.
    """

    name: str
    """An optional name for the participant.

    Provides the model information to differentiate between participants of the same
    role.
    """

    refusal: Optional[str]
    """The refusal message by the assistant."""

    tool_calls: List[ChatCompletionMessageToolCallParam]
    """The tool calls generated by the model, such as function calls."""

    latency_ms: Optional[int]
    """Time spent waiting on this specific LLM API call in milliseconds."""

    usage: Optional[MessageUsage]
    """Token usage and cost for the LLM call that produced this assistant message.

    Set per-call (one record per LLM response, not per logical turn). Stripped
    before sending messages back to providers via KILN_ONLY_MESSAGE_FIELDS.
    Per-call latency lives on the message's `latency_ms` field — MessageUsage
    intentionally does not carry latency.
    """


class ChatCompletionToolMessageParamWrapper(TypedDict, total=False):
    """A tool-result message in a trace.

    Almost a copy of the OpenAI SDK's ChatCompletionToolMessageParam, with the
    `content` type change described in this module's docstring, and the Kiln-only
    fields below - all of them stripped before the message is sent to a provider.
    """

    content: Required[Union[str, List[ContentPart]]]
    """The contents of the tool message."""

    role: Required[Literal["tool"]]
    """The role of the messages author, in this case `tool`."""

    tool_call_id: Required[str]
    """Tool call that this message is responding to."""

    kiln_task_tool_data: Optional[str]
    """The data for the Kiln task tool that this message is responding to.

    Formatted as `<project_id>:::<tool_id>:::<task_id>:::<run_id>`
    """

    is_error: Optional[bool]
    """Whether this tool message represents an error result."""

    error_message: Optional[str]
    """Human-readable error description when is_error is True."""


ChatCompletionMessageParam: TypeAlias = Union[
    ChatCompletionDeveloperMessageParamWrapper,
    ChatCompletionSystemMessageParamWrapper,
    ChatCompletionUserMessageParamWrapper,
    ChatCompletionAssistantMessageParamWrapper,
    ChatCompletionToolMessageParamWrapper,
    ChatCompletionFunctionMessageParam,
]


KILN_ONLY_MESSAGE_FIELDS: frozenset[str] = frozenset(
    {
        "latency_ms",
        "is_error",
        "error_message",
        "kiln_task_tool_data",
        "usage",
    }
)
"""Per-message fields kept on traces for UI/diagnostics. Providers reject unknown
keys, so these are stripped before sending to LiteLLM. Add new Kiln-only message
fields here when extending the wrappers above."""


def sanitize_messages_for_provider(messages: Iterable[Any]) -> list[Any]:
    """Return a copy of ``messages`` with ``KILN_ONLY_MESSAGE_FIELDS`` removed
    from any dict entries. Non-dict entries (e.g. LiteLLM ``Message`` objects)
    pass through unchanged. The input list and its dicts are not mutated."""
    sanitized: list[Any] = []
    for message in messages:
        # Traces mix TypedDict messages (which may carry kiln-only fields) with
        # LiteLLM Message pydantic objects returned from prior calls (which never
        # do). Only dicts need stripping; pass other types through untouched.
        if isinstance(message, dict):
            sanitized.append(
                {k: v for k, v in message.items() if k not in KILN_ONLY_MESSAGE_FIELDS}
            )
        else:
            sanitized.append(message)
    return sanitized


_RE_READABLE_TYPES: tuple[type, ...] = (
    str,
    bytes,
    bytearray,
    memoryview,
    list,
    tuple,
    set,
    frozenset,
    Mapping,
    BaseModel,
)
"""Types that must not be treated as a lazy iterable.

Two groups. The first (list, tuple, set, ...) can be read as many times as you like,
so there is nothing to rescue. The second is the dangerous one: a str, a bytes-like
object, a Mapping and a pydantic BaseModel are all iterable, and iterating them
yields something that is *not* their content - characters, ints, keys, and
``(name, value)`` pairs respectively. Draining one would not preserve the value, it
would replace it with a mangled one.
"""


def _is_lazy_iterable(value: Any) -> bool:
    """True if reading ``value`` consumes it, so it must be materialized before
    anything else gets a chance to read it. See `_RE_READABLE_TYPES`."""
    return isinstance(value, Iterable) and not isinstance(value, _RE_READABLE_TYPES)


def materialize_lazy_content(trace: Any) -> Any:
    """Normalize a lazily-iterable ``content`` to a list, in front of union validation.

    The wrappers declare ``content`` as ``List[T]``, so a list arrives whole. A caller
    can still hand over any other iterable - a generator, a ``map`` object - and that
    is where pydantic's smart union bites: it tries its members in order, and the
    members whose role does not match still drain the iterator before they fail. By the
    time the matching member runs there is nothing left to read, and the message
    validates to ``content: []`` - silently, with the parts gone. Draining it here,
    once, is what makes that safe. The trace container itself gets the same treatment:
    pydantic accepts a tuple or a generator for a ``list[T]`` field, so a lazy container
    would otherwise carry its lazy messages straight past this guard.

    Scoped to ``content`` deliberately, and it needs to stay that way. Iterating a
    pydantic model yields its ``(name, value)`` pairs, so a walk over "any iterable
    value" would turn a message's ``usage`` into a list of pairs.

    Writes the materialized list back into the caller's message when it can, rather
    than into a copy. Draining a generator is destructive either way, so a copy would
    leave the caller holding a spent one: validate or serialize the same trace twice
    and the second pass sees ``content: []``. Normalizing in place is what makes those
    repeatable. Anything with no lazy content is passed through untouched, including
    values pydantic should reject with its own error message.
    """
    if not isinstance(trace, list):
        # Pydantic lax mode accepts any of these for a `list[T]` field, so the walk
        # below has to reach the messages inside them. Everything else is passed
        # through for pydantic to reject with its own error message.
        if isinstance(trace, Iterable) and not isinstance(
            trace, (str, bytes, bytearray, memoryview, Mapping, BaseModel)
        ):
            trace = list(trace)
        else:
            return trace

    materialized: list[Any] = []
    for message in trace:
        if isinstance(message, Mapping):
            content = message.get("content")
            if _is_lazy_iterable(content):
                if isinstance(message, MutableMapping):
                    message["content"] = list(content)
                else:
                    # A read-only Mapping (MappingProxyType, ...) cannot be normalized
                    # in place. Copying it is still better than letting the union drain
                    # it, even though the caller keeps the spent iterator.
                    message = {**message, "content": list(content)}
        materialized.append(message)
    return materialized


def _materialize_lazy_content_before_serializing(
    trace: Any, handler: SerializerFunctionWrapHandler
) -> list["ChatCompletionMessageParam"]:
    """Materialize, then hand over to pydantic's own serializer for this field.

    The return annotation is load-bearing: without it pydantic types the field's
    serialization schema as ``Any``, and every OpenAPI response carrying a trace
    degrades to ``unknown``.
    """
    return handler(materialize_lazy_content(trace))


Trace: TypeAlias = Annotated[
    list[ChatCompletionMessageParam],
    BeforeValidator(materialize_lazy_content),
    WrapSerializer(_materialize_lazy_content_before_serializing),
]
"""A trace as a pydantic model should declare it.

Use this, not a bare ``list[ChatCompletionMessageParam]``: the two guards are what
stop a lazily-iterable ``content`` from being drained to nothing - see
:func:`materialize_lazy_content`.

Validation covers a trace passed to the constructor or assigned to the field (given
``validate_assignment``). Serialization covers what validation cannot see: appending
a message to an already-validated trace list in place runs no validator at all, so
without the second guard the first save would write the message and every save after
it would write ``content: []``.
"""


_trace_adapter: TypeAdapter[list[ChatCompletionMessageParam]] = TypeAdapter(
    list[ChatCompletionMessageParam]
)


def serialize_trace(trace: list[ChatCompletionMessageParam]) -> str:
    """Serialize a trace to the pretty-printed JSON that Kiln stores and displays.

    Not `json.dumps`: a validated trace is not plain data. Pydantic coerces the
    per-message `usage` key to a `MessageUsage` model (both in memory and when a
    TaskRun is loaded back off disk), and the stdlib encoder cannot serialize it.
    For an otherwise-plain trace this returns byte-for-byte what `json.dumps(...,
    indent=2, ensure_ascii=False)` returned, so stored traces render unchanged.
    """
    # warnings=False: every message with a key the wrappers don't declare or a
    # `Usage` in the `usage` slot fails to match a union member and emits a
    # six-line serializer warning - on every message, on every eval-results
    # request. The mismatch is not a defect: pydantic then falls
    # back to duck-typed inference, which is exactly what keeps the output
    # byte-identical to the `json.dumps` this replaced. Silencing it loses no signal
    # a test wouldn't catch first - TestSerializeTrace pins that parity, including
    # the unknown-key and unknown-role cases that rely on the fallback, so a pydantic
    # upgrade that tightened union serialization fails there rather than in a log.
    #
    # materialize_lazy_content first: `dump_json` runs serializers, not validators, so
    # the `Trace` alias does not protect a trace that has not been through a model.
    # Without it a lazy `content` is drained by the serializer and this function is
    # destructive - correct on the first call, `content: []` on the second.
    return _trace_adapter.dump_json(
        materialize_lazy_content(trace), indent=2, warnings=False
    ).decode()


def trace_has_pending_client_tool_calls(
    trace: list[ChatCompletionMessageParam] | None,
) -> bool:
    """Return True if the trace ends with an assistant message awaiting client tool results.

    Structured-output flows use an internal ``task_response`` tool call; traces that end
    with only those calls are complete from the client's perspective for external tools.
    """
    if not trace:
        return False
    last_msg = trace[-1]
    if last_msg.get("role") != "assistant":
        return False
    tool_calls = last_msg.get("tool_calls") or []
    return any(
        isinstance(tc, dict)
        and (tc.get("function") or {}).get("name") != "task_response"
        for tc in tool_calls
    )
