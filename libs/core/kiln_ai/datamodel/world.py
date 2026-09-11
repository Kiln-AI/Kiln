"""Worlds: an OpenEnv environment that plays the tool set an agent sees, so evals can
read and write against state the eval owns.

A **world** is a pointer to an OpenEnv environment (https://github.com/huggingface/OpenEnv)
that is already running at `env_url`. Kiln never starts or stops environments, and holds
none of their code: the environment implements OpenEnv's `reset`, `step` and `state`;
its tools are served by `step(CallToolAction)` and discovered with `step(ListToolsAction)`.
Nothing about a world is Kiln-specific: an env author writes OpenEnv code and no Kiln
code. The environment's reported name and version key the traces generated against it.

An eval input carries a `WorldReset`: the world plus `reset_kwargs`, the keyword
arguments of the environment's `reset`. An **episode** is one reset-to-close run on a session of
that environment: the state one eval job acts on. Its outcome is recorded on the trace
as `Episode`, never stored as a project artifact.

A run config chooses the environment's tools explicitly, by listing them as
`kiln_tool::world::<world_id>::<tool_name>`; nothing is substituted for the project's tools
behind the model's back. An episode is started only when the run config lists the
input's world's tools; a run config without world tools runs the same input against
project tools. A run config that lists the project's own version of a tool the world serves is
refused for such an input, so a case that writes can never reach the project's own backend by
accident; project tools the world does not serve are always allowed. The eval runner also
refuses world tools without a world on the input, or from a different world. Because
the environment serves the same function names as the project tools, the trace and
tool-call checks read the same.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field, JsonValue

from kiln_ai.datamodel.basemodel import FilenameString, KilnParentedModel

if TYPE_CHECKING:
    from kiln_ai.tools.base_tool import ToolCallDefinition


class OpenEnvTool(BaseModel):
    """One tool an environment serves, as returned by `step(ListToolsAction)`.

    A runtime value object, never persisted: the environment is the source of truth."""

    name: str = Field(min_length=1)
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)

    def toolcall_definition(self) -> "ToolCallDefinition":
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema or {"type": "object", "properties": {}},
            },
        }


class WorldReset(BaseModel):
    """Reset this world with these keyword arguments before the run; the reset starts
    the episode the trace records.

    `reset_kwargs` is opaque to Kiln: it is passed as the keyword arguments of the
    environment's `reset` (a dataset or scenario identifier, a seed, a clock override). It is
    part of the trace key, so two inputs with different kwargs never share a generation.
    """

    world_id: str = Field(min_length=1, description="The World to run in.")
    reset_kwargs: dict[str, JsonValue] = Field(
        default_factory=dict,
        description="Keyword arguments for the environment's reset(), passed verbatim. Which keywords exist is the environment's business, e.g. which dataset or scenario to start from, a seed, a clock override.",
    )


class Episode(BaseModel):
    """One reset-to-close run on a world's environment, recorded on the trace of the
    task run that used it. The world's tools ran inside the episode; any other tools
    in the run config ran as themselves, outside the world.

    Persisted on `TaskRun.episode` so graders (including judges added later, which
    reuse the same trace) can read what the run left behind. The live session is closed
    at finalize; `state` is the durable record.
    """

    episode_id: str = Field(min_length=1)
    world_id: str = Field(min_length=1)
    world_version: str | None = Field(
        default=None,
        description="The environment's name@version as its server reported it when the episode started: what produced this state. Kiln trusts a version to be immutable.",
    )
    reset_kwargs: dict[str, JsonValue] = Field(
        default_factory=dict,
        description="The reset() keyword arguments this episode was started from.",
    )
    metadata: dict[str, JsonValue] = Field(
        default_factory=dict,
        description="What the environment reported in its reset observation's metadata: facts about the episode's starting state that judges may want, such as the scenario it started from or the clock it runs on.",
    )
    state: dict[str, JsonValue] | None = Field(
        default=None,
        description="The environment's state() after generation, read when the episode ends. Whatever the environment chooses to report: a diff against its starting state, counters, an episode summary.",
    )

    def to_sandbox_dict(self) -> dict[str, JsonValue]:
        """The stdlib-only shape handed to sandboxed tools and code scorers."""
        return {
            "episode_id": self.episode_id,
            "world_id": self.world_id,
            "world_version": self.world_version,
            "reset_kwargs": self.reset_kwargs,
            "metadata": self.metadata,
            "state": self.state,
        }


class World(KilnParentedModel):
    """A pointer to a running OpenEnv environment."""

    name: FilenameString = Field(description="User-facing display name.")
    description: str | None = Field(default=None)
    env_url: str | None = Field(
        default=None,
        description="Base URL of the running OpenEnv server for this world (e.g. http://127.0.0.1:8004). Kiln connects to it; it never starts one.",
    )
