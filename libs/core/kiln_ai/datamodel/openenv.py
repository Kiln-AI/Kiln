"""OpenEnv environments that serve the tool set an agent sees, so evals can read and
write against state the eval owns.

An **OpenEnv server** is Kiln's saved pointer to an OpenEnv environment (https://github.com/openenv/OpenEnv)
that is already running at `url`. Kiln never starts or stops environments, and holds
none of their code: the environment implements OpenEnv's `reset`, `step` and `state`;
its tools are served by `step(CallToolAction)` and discovered with `step(ListToolsAction)`.
Nothing about an environment is Kiln-specific: an env author writes OpenEnv code and no Kiln
code.

The environment's reported name and version (from its `/metadata`) key the traces
generated against it, together with the input's reset. Kiln trusts a version to be
immutable: an environment whose behaviour changes without a new version has its old
traces, and their final states, reused against the new code. OpenEnv's default
`get_metadata()` reports the class name and version `1.0.0` for every environment, so an
environment used with Kiln should override `get_metadata()` and bump its version
whenever its tools or state change.

Each eval job holds one session on the environment for its whole episode, and Kiln runs
up to 25 eval jobs at once per eval run. Run an environment's server with `max_concurrent_envs`
of at least 25 (more if evals on the same environment may overlap); OpenEnv's default is 1,
and allowing more than one requires the environment to keep its state per session
(`SUPPORTS_CONCURRENT_SESSIONS = True`). A job that finds the server full fails with a
capacity error before any model call, and re-running the eval runs only the jobs that
failed.

Outside evals, a run whose tools reach an OpenEnv server (directly, through code tools or
through Kiln task tools) holds one session for the run too, reset with the run's
`openenv_reset_kwargs`, and records its episode on the run (see
`kiln_ai.openenv.run_session`).

An eval input carries an `OpenEnvReset`: the OpenEnv server plus `reset_kwargs`, the keyword
arguments of the environment's `reset`. An **episode** is one reset-to-close run on a session of
that environment: the state one eval job acts on. Its outcome is recorded on the trace
as `OpenEnvEpisode`, never stored as a project artifact.

A run config chooses the OpenEnv server's tools explicitly, by listing them as
`kiln_tool::openenv::<openenv_server_id>::<tool_name>`; nothing is substituted for the project's tools
behind the model's back. An episode is started only when the run config lists the
input's OpenEnv server's tools; a run config without OpenEnv tools runs the same input against
project tools. A run config that lists the project's own version of a tool the environment serves is
refused for such an input; project tools the environment does not serve are always allowed. The
check covers the tools a run config lists directly. It does not follow tools reached
through another tool: a Kiln task tool's own run config, a code tool's allowlist, or the
tools of an MCP-type run config can still reach the project's version of a tool the environment
serves. The eval runner also refuses OpenEnv tools without an OpenEnv server on the input, or from a
different OpenEnv server. Because
the environment serves the same function names as the project tools, the trace and
tool-call checks read the same.
"""

from __future__ import annotations

from typing import Annotated, Any
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, JsonValue, StringConstraints, field_validator

from kiln_ai.datamodel.basemodel import FilenameString, KilnParentedModel


class OpenEnvTool(BaseModel):
    """One tool an environment serves, as returned by `step(ListToolsAction)`.

    A runtime value object, never persisted: the environment is the source of truth."""

    name: str = Field(
        min_length=1, description="The tool's function name, as the model sees it."
    )
    description: str = Field(
        default="", description="The tool's description, as the model sees it."
    )
    input_schema: dict[str, Any] = Field(
        default_factory=dict, description="JSON schema of the tool's arguments."
    )


class OpenEnvReset(BaseModel):
    """Start a new episode on the OpenEnv server named by `openenv_server_id`, by calling the
    environment's `reset()` with these keyword arguments before the run. The trace records
    that episode.

    `reset_kwargs` is opaque to Kiln: it is passed as the keyword arguments of the
    environment's `reset`, and which keywords exist depends on the environment. The
    trace key carries a digest of the whole reset, so an input whose reset is edited
    after its trace was made generates a new one rather than reusing it.
    """

    openenv_server_id: str = Field(
        min_length=1, description="ID of the OpenEnv server to start the episode on."
    )
    reset_kwargs: dict[str, JsonValue] = Field(
        default_factory=dict,
        description="Keyword arguments for the environment's reset(), passed verbatim. Which keywords exist depends on the environment.",
    )


class OpenEnvEpisode(BaseModel):
    """One reset-to-close run on an environment, recorded on the trace of the
    task run that used it. The environment's tools ran inside the episode; any other tools
    in the run config ran as themselves, outside the environment.

    Persisted on `TaskRun.openenv_episode` so graders (including judges added later,
    which reuse the same trace) can read what the run left behind. The live session is
    closed when the episode ends; `final_state` is the durable record.
    """

    reset: OpenEnvReset = Field(
        description="The OpenEnv server and reset() keyword arguments this episode was started from: the input's openenv_reset."
    )
    episode_id: str = Field(
        min_length=1,
        description="Kiln's id for this episode, passed to the environment's reset() as `episode_id`.",
    )
    openenv_version: str = Field(
        min_length=1,
        description="The environment's name@version as its server reported it when the episode started (not the version of the openenv package): what produced this state. Kiln trusts a version to be immutable.",
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
        """The stdlib-only shape handed to code scorers as `openenv_episode`."""
        return {
            "reset": {
                "openenv_server_id": self.reset.openenv_server_id,
                "reset_kwargs": self.reset.reset_kwargs,
            },
            "episode_id": self.episode_id,
            "openenv_version": self.openenv_version,
            "reset_metadata": self.reset_metadata,
            "final_state": self.final_state,
        }


class NamedResetKwargs(BaseModel):
    """Reset keyword arguments saved under a name, so a run can pick them by name.

    Shown in the UI as an Environment Preset. A run records the kwargs it used, not
    the name, because a preset can be renamed or removed later."""

    name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)
    ] = Field(description="User-facing name, unique within its environment.")
    description: str | None = Field(
        default=None,
        description="User-facing notes on what this preset starts the environment with.",
    )
    reset_kwargs: dict[str, JsonValue] = Field(
        default_factory=dict,
        description="Keyword arguments for the environment's reset(), passed verbatim.",
    )


class OpenEnvServer(KilnParentedModel):
    """Kiln's saved pointer to a running OpenEnv environment.

    Lives under a project (`project.openenv_servers()`). `url` may be None while the record is
    being set up, but an eval that runs in this OpenEnv server needs it set. Kiln reads the
    environment's identity and tools from the server at `url` and holds none of its code."""

    name: FilenameString = Field(description="User-facing display name.")
    description: str | None = Field(
        default=None, description="User-facing notes about the OpenEnv server."
    )
    url: str | None = Field(
        default=None,
        description="Base URL of the running OpenEnv server (e.g. http://127.0.0.1:8000). Kiln connects to it; it never starts one.",
    )
    named_reset_kwargs: list[NamedResetKwargs] = Field(
        default_factory=list,
        description="Named reset kwargs a run can start the environment with, in the order they were added. The first is the default.",
    )
    is_archived: bool = Field(
        default=False,
        description="Whether the OpenEnv server is archived. An archived server's tools aren't offered in tool pickers, but run configs that already list them still run.",
    )

    @field_validator("named_reset_kwargs")
    @classmethod
    def unique_option_names(
        cls, value: list[NamedResetKwargs]
    ) -> list[NamedResetKwargs]:
        seen: set[str] = set()
        for option in value:
            if option.name in seen:
                raise ValueError(
                    f"An Environment Preset named {option.name} already exists."
                )
            seen.add(option.name)
        return value

    @classmethod
    def type_name(cls) -> str:
        # The default snake-cases the class name to "open_env_server"; OpenEnv is one
        # word, spelled "openenv" like the upstream package.
        return "openenv_server"

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str | None) -> str | None:
        """Require an http(s) URL with a host, so a typo fails when the OpenEnv server is saved
        rather than when an eval first connects."""
        if value is None:
            return None
        parts = urlsplit(value)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ValueError(
                f"url must be an http:// or https:// URL with a host, got {value!r}"
            )
        return value
