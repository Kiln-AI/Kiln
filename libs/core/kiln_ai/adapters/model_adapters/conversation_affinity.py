import hashlib
import json
from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import Any

from kiln_ai.datamodel.datamodel_enums import ModelProviderName

PROMPT_KEYED_PARAM_BY_PROVIDER: Mapping[ModelProviderName, str] = MappingProxyType(
    {
        ModelProviderName.openai: "prompt_cache_key",
        ModelProviderName.together_ai: "prompt_cache_key",
    }
)
"""The cache routing param for each provider that documents one. Its value is a
hash of the leading system prompt, so every run of one prompt shares a cache.
LiteLLM forwards these params to most other providers too, and those may reject
them, so they are sent only to the providers listed here."""

CONVERSATION_KEYED_PARAM_BY_PROVIDER: Mapping[ModelProviderName, str] = (
    MappingProxyType({ModelProviderName.openrouter: "session_id"})
)
"""The session param that pins a conversation to one backend server, for each
provider that documents one. Sent only to the providers listed here, for the same
reason as ``PROMPT_KEYED_PARAM_BY_PROVIDER``.
OpenRouter: https://openrouter.ai/docs/guides/best-practices/prompt-caching"""

# OpenAI caps prompt_cache_key at 64 characters.
_AFFINITY_KEY_HEX_CHARS = 32

_SYSTEM_ROLES = frozenset({"system", "developer"})


def conversation_affinity_key(messages: Sequence[Any]) -> str | None:
    """A routing key shared by every request of one conversation.

    The key hashes the role and content of each message up to and including the
    first user message. Later turns resend that opening unchanged as their prior
    trace, so all turns (and the tool-call rounds within them) get the same key,
    while conversations that open differently get different keys.

    Returns None when ``messages`` has no user message.
    """
    opening: list[tuple[Any, Any]] = []
    for message in messages:
        role = _message_field(message, "role")
        opening.append((role, _message_field(message, "content")))
        if role == "user":
            return _digest(opening)
    return None


def prompt_affinity_key(messages: Sequence[Any]) -> str | None:
    """A routing key shared by every request that opens with the same system prompt.

    The key hashes the role and content of the leading system and developer
    messages, so runs of one task prompt share it across conversations, and every
    turn of a conversation gets the same key. Without a leading system or
    developer message, this is ``conversation_affinity_key(messages)``.
    """
    system_opening: list[tuple[Any, Any]] = []
    for message in messages:
        role = _message_field(message, "role")
        if role not in _SYSTEM_ROLES:
            break
        system_opening.append((role, _message_field(message, "content")))
    if not system_opening:
        return conversation_affinity_key(messages)
    return _digest(system_opening)


def affinity_completion_kwargs(
    provider_name: ModelProviderName, messages: Sequence[Any]
) -> dict[str, str]:
    """LiteLLM completion kwargs that route the request for ``messages``.

    Always includes ``litellm_session_id``, set to ``conversation_affinity_key``.
    LiteLLM sends it to Fireworks as the ``x-session-affinity`` header, sends it to
    no other provider's API, and passes it to LiteLLM logging callbacks as the
    session id. Providers in ``CONVERSATION_KEYED_PARAM_BY_PROVIDER`` also get their
    session param set to the conversation key, and providers in
    ``PROMPT_KEYED_PARAM_BY_PROVIDER`` get their cache param set to
    ``prompt_affinity_key``.

    Returns no kwargs when ``messages`` has no user message.
    """
    conversation_key = conversation_affinity_key(messages)
    if conversation_key is None:
        return {}
    kwargs = {"litellm_session_id": conversation_key}
    conversation_param = CONVERSATION_KEYED_PARAM_BY_PROVIDER.get(provider_name)
    if conversation_param is not None:
        kwargs[conversation_param] = conversation_key
    prompt_param = PROMPT_KEYED_PARAM_BY_PROVIDER.get(provider_name)
    if prompt_param is not None:
        kwargs[prompt_param] = prompt_affinity_key(messages) or conversation_key
    return kwargs


def _digest(pairs: list[tuple[Any, Any]]) -> str:
    serialized = json.dumps(pairs, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[
        :_AFFINITY_KEY_HEX_CHARS
    ]


def _message_field(message: Any, field: str) -> Any:
    if isinstance(message, Mapping):
        return message.get(field)
    return getattr(message, field, None)
