"""Fixtures for the grounding agent's tests: the test OpenEnv server from
`kiln_ai.openenv.testing`, and a scripted stand-in for the model."""

import copy
import itertools
import json
from collections.abc import Awaitable, Callable, Iterator
from typing import Any
from unittest.mock import patch

import pytest
from litellm.types.utils import ModelResponse

from kiln_ai.adapters.ml_model_list import KilnModelProvider
from kiln_ai.adapters.model_adapters.litellm_adapter import LiteLlmAdapter
from kiln_ai.datamodel.datamodel_enums import ModelProviderName
from kiln_ai.datamodel.openenv import OpenEnvServer
from kiln_ai.datamodel.project import Project
from kiln_ai.openenv.session_manager import OpenEnvSessionManager
from kiln_ai.openenv.testing import serve_in_thread


@pytest.fixture
def project(tmp_path):
    path = tmp_path / "proj" / "project.kiln"
    path.parent.mkdir(parents=True)
    p = Project(name="proj", path=path)
    p.save_to_file()
    return p


@pytest.fixture
def one_session_url():
    """A server that holds one session, so a leaked episode blocks the next reset."""
    with serve_in_thread(max_sessions=1) as base_url:
        yield base_url


@pytest.fixture
def openenv_server(project, one_session_url):
    server = OpenEnvServer(name="counter", parent=project, url=one_session_url)
    server.save_to_file()
    return server


@pytest.fixture
async def session_manager():
    manager = OpenEnvSessionManager()
    try:
        yield manager
    finally:
        await manager.shutdown()


@pytest.fixture
def server_is_free(openenv_server) -> Callable[[], Awaitable[None]]:
    """Fails unless the one-session server can start an episode, which it can't while
    an episode is left open."""

    async def check() -> None:
        manager = OpenEnvSessionManager()
        try:
            episode = await manager.start_episode(openenv_server, {})
            await manager.release(episode)
        finally:
            await manager.shutdown()

    return check


ModelReply = tuple[ModelResponse, Any]

_call_ids = itertools.count()


def model_reply(
    content: str | None = None, *tool_calls: tuple[str, dict[str, Any]]
) -> ModelReply:
    """One model response: text, tool calls, or both. Each reply reports 10 input and
    2 output tokens."""
    calls = [
        {
            "id": f"call_{next(_call_ids)}",
            "type": "function",
            "function": {
                "name": name,
                "arguments": json.dumps(args, ensure_ascii=False),
            },
        }
        for name, args in tool_calls
    ]
    response = ModelResponse(
        model="gpt-4",
        choices=[{"message": {"content": content, "tool_calls": calls or None}}],
        usage={"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
    )
    return response, response.choices[0]


class ScriptedModel:
    """Answers each completion call with the next scripted reply, and records the
    messages each call was sent. A reply may be a coroutine function, awaited in place
    of a reply (to stall, for example)."""

    def __init__(self) -> None:
        self.replies: list[ModelReply | Callable[[], Awaitable[ModelReply]]] = []
        self.sent: list[list[Any]] = []

    def script(self, *replies: ModelReply | Callable[[], Awaitable[ModelReply]]):
        self.replies.extend(replies)

    async def _complete(self, **kwargs: Any) -> ModelReply:
        self.sent.append(kwargs["messages"])
        if not self.replies:
            raise AssertionError("The model was called more often than scripted.")
        reply = self.replies.pop(0)
        return await reply() if callable(reply) else reply


@pytest.fixture
def scripted_model() -> Iterator[ScriptedModel]:
    """Every Kiln adapter in the test talks to this model instead of a provider."""
    model = ScriptedModel()
    provider = KilnModelProvider(name=ModelProviderName.openai, model_id="gpt-4")

    async def completion_kwargs(_provider, messages, *_rest) -> dict[str, Any]:
        return {"messages": copy.deepcopy(messages)}

    with (
        patch(
            "kiln_ai.adapters.adapter_registry.kiln_model_provider_from",
            return_value=provider,
        ),
        patch.object(LiteLlmAdapter, "model_provider", return_value=provider),
        patch.object(
            LiteLlmAdapter, "build_completion_kwargs", side_effect=completion_kwargs
        ),
        patch.object(
            LiteLlmAdapter, "acompletion_checking_response", side_effect=model._complete
        ),
    ):
        yield model


@pytest.fixture
def few_tool_rounds() -> Iterator[None]:
    """The adapter's cap on tool rounds in one run, lowered to 3."""
    with patch(
        "kiln_ai.adapters.model_adapters.litellm_adapter.MAX_TOOL_CALLS_PER_TURN", 3
    ):
        yield
