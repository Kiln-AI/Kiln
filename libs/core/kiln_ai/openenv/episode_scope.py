"""One episode on an OpenEnv server, bound as the current episode for a block of code.

Used where the caller, not the adapter, owns the episode: an eval job generating a trace,
and a synthetic user batch driving a grounded case. Every turn and tool call inside the
block runs in the same episode, and the block's end settles it with the environment's
final state.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator

from pydantic import JsonValue

from kiln_ai.datamodel.openenv import OpenEnvEpisode, OpenEnvServer, OpenEnvTool
from kiln_ai.openenv.session_manager import OpenEnvSessionManager
from kiln_ai.run_context import EpisodeContext, reset_episode, set_episode


@dataclass
class EpisodeScope:
    episode: OpenEnvEpisode
    """The live episode, as it was started."""
    _ended: OpenEnvEpisode | None = None

    @property
    def ended(self) -> OpenEnvEpisode:
        """The episode with the environment's final state, once the scope has ended
        without an error. `final_state` is None when the session was already gone."""
        if self._ended is None:
            raise RuntimeError("The episode scope has not ended yet.")
        return self._ended


@asynccontextmanager
async def openenv_episode_scope(
    manager: OpenEnvSessionManager,
    server: OpenEnvServer,
    reset_kwargs: dict[str, JsonValue],
    tools: dict[str, OpenEnvTool],
) -> AsyncIterator[EpisodeScope]:
    """Start an episode, bind it as the current episode for the block, then end it.

    `tools` are the server's tools by name, as `list_tools` returned them. On a clean exit
    the episode is ended (its state read, its session closed) and kept as `scope.ended`.
    On any error, cancellation included, its session is released and the error re-raised.
    Errors starting or ending the episode propagate as the session manager raised them."""
    episode = await manager.start_episode(server, reset_kwargs)
    scope = EpisodeScope(episode=episode)
    token = set_episode(
        EpisodeContext(
            episode=episode,
            openenv_server=server,
            session_manager=manager,
            tools=tools,
        )
    )
    try:
        try:
            yield scope
        finally:
            reset_episode(token)
    except BaseException:
        await manager.release(episode)
        raise
    scope._ended = await manager.end_episode(episode)
