"""Worlds: an OpenEnv environment that plays the tool set an agent sees, so evals can
read and write against state the eval owns.

A **world** is a pointer to an OpenEnv environment (https://github.com/huggingface/OpenEnv)
that is already running at `env_url`. Kiln never starts or stops environments, and holds
none of their code: the environment implements OpenEnv's `reset`, `step` and `state`;
its tools are served by `step(CallToolAction)` and discovered with `step(ListToolsAction)`.
Nothing about a world is Kiln-specific: an env author writes OpenEnv code and no Kiln
code.

The environment's reported name and version (from its `/metadata`) key the traces
generated against it, together with the input's reset. Kiln trusts a version to be
immutable: an environment whose behaviour changes without a new version has its old
traces, and their final states, reused against the new code. OpenEnv's default
`get_metadata()` reports the class name and version `1.0.0` for every environment, so an
environment used as a world should override `get_metadata()` and bump its version
whenever its tools or state change.

Each eval job holds one session on the environment for its whole episode, and Kiln runs
up to 25 eval jobs at once per eval run. Run a world's server with `max_concurrent_envs`
of at least 25 (more if evals on the same world may overlap); OpenEnv's default is 1,
and allowing more than one requires the environment to keep its state per session
(`SUPPORTS_CONCURRENT_SESSIONS = True`). A job that finds the server full fails with a
capacity error before any model call, and re-running the eval runs only the jobs that
failed.

An eval input carries a `WorldReset`: the world plus `reset_kwargs`, the keyword
arguments of the environment's `reset`. An **episode** is one reset-to-close run on a session of
that environment: the state one eval job acts on. Its outcome is recorded on the trace
as `WorldEpisode`, never stored as a project artifact.

A run config chooses the environment's tools explicitly, by listing them as
`kiln_tool::world::<world_id>::<tool_name>`; nothing is substituted for the project's tools
behind the model's back. An episode is started only when the run config lists the
input's world's tools; a run config without world tools runs the same input against
project tools. A run config that lists the project's own version of a tool the world serves is
refused for such an input; project tools the world does not serve are always allowed. The
check covers the tools a run config lists directly. It does not follow tools reached
through another tool: a Kiln task tool's own run config, a code tool's allowlist, or the
tools of an MCP-type run config can still reach the project's version of a tool the world
serves. The eval runner also refuses world tools without a world on the input, or from a
different world. Because
the environment serves the same function names as the project tools, the trace and
tool-call checks read the same.
"""

from __future__ import annotations

from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, JsonValue, field_validator

from kiln_ai.datamodel.basemodel import FilenameString, KilnParentedModel


class OpenEnvTool(BaseModel):
    """One tool an environment serves, as returned by `step(ListToolsAction)`.

    A runtime value object, never persisted: the environment is the source of truth."""

    name: str = Field(min_length=1)
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)


class WorldReset(BaseModel):
    """Reset this world with these keyword arguments before the run; the reset starts
    the episode the trace records.

    `reset_kwargs` is opaque to Kiln: it is passed as the keyword arguments of the
    environment's `reset` (a dataset or scenario identifier, a seed, a clock override). The
    trace key carries a digest of the whole reset, so an input whose reset is edited
    after its trace was made generates a new one rather than reusing it.
    """

    world_id: str = Field(min_length=1, description="The World to run in.")
    reset_kwargs: dict[str, JsonValue] = Field(
        default_factory=dict,
        description="Keyword arguments for the environment's reset(), passed verbatim. Which keywords exist is the environment's business, e.g. which dataset or scenario to start from, a seed, a clock override.",
    )


class WorldEpisode(BaseModel):
    """One reset-to-close run on a world's environment, recorded on the trace of the
    task run that used it. The world's tools ran inside the episode; any other tools
    in the run config ran as themselves, outside the world.

    Persisted on `TaskRun.world_episode` so graders (including judges added later,
    which reuse the same trace) can read what the run left behind. The live session is
    closed when the episode ends; `final_state` is the durable record.
    """

    reset: WorldReset = Field(
        description="The world and reset() keyword arguments this episode was started from: the input's world_reset."
    )
    episode_id: str = Field(min_length=1)
    world_version: str = Field(
        min_length=1,
        description="The environment's name@version as its server reported it when the episode started: what produced this state. Kiln trusts a version to be immutable.",
    )
    reset_metadata: dict[str, JsonValue] = Field(
        default_factory=dict,
        description="What the environment reported in the observation metadata when the episode was reset: facts about the starting state that judges may want, such as the scenario it started from or the clock it runs on.",
    )
    final_state: dict[str, JsonValue] | None = Field(
        default=None,
        description="The environment's state() after generation, read when the episode ends. Whatever the environment chooses to report: a diff against its starting state, counters, an episode summary.",
    )

    def to_sandbox_dict(self) -> dict[str, JsonValue]:
        """The stdlib-only shape handed to code scorers as `world_episode`."""
        return {
            "reset": {
                "world_id": self.reset.world_id,
                "reset_kwargs": self.reset.reset_kwargs,
            },
            "episode_id": self.episode_id,
            "world_version": self.world_version,
            "reset_metadata": self.reset_metadata,
            "final_state": self.final_state,
        }


class World(KilnParentedModel):
    """A pointer to a running OpenEnv environment."""

    name: FilenameString = Field(description="User-facing display name.")
    description: str | None = Field(default=None)
    kind: Literal["openenv"] = Field(
        default="openenv",
        description="The kind of environment behind env_url. Only OpenEnv today.",
    )
    env_url: str | None = Field(
        default=None,
        description="Base URL of the running OpenEnv server for this world (e.g. http://127.0.0.1:8004). Kiln connects to it; it never starts one.",
    )

    @field_validator("env_url")
    @classmethod
    def validate_env_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parts = urlsplit(value)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ValueError(
                f"env_url must be an http:// or https:// URL with a host, got {value!r}"
            )
        return value
