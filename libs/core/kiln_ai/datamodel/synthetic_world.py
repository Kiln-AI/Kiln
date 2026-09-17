"""Synthetic worlds: a replica of the tool set an agent sees, launched as isolated
instances so evals can read and write without touching a real backend.

On disk under a project:

    synthetic_worlds/<id> - <name>/synthetic_world.kiln          SyntheticWorld
        lib/                                                      shared world code
        tools/<id> - <name>/synthetic_tool.kiln + tool.py         SyntheticTool
        fixtures/<fixture_id>/...                                 local-files launcher data

A **world** is the code that plays a client's tool set: each `SyntheticTool` declares
the real tool id it replaces, and the world names the **launcher** that creates its
instances. An eval input carries a `SyntheticEnvironment`: the world plus an opaque
launch `config` the launcher understands (a fixture id, a seed, an OpenEnv task).
An **instance** is what a launch returns: isolated state one eval job acts on, recorded
on the trace as `SyntheticInstance` rather than stored as a project artifact.

Kiln never interprets a launch config or an instance's contents. It passes the config to
the launcher, hands the instance to tools and graders, keys traces by the config and the
launcher's content version, and decides when an instance can be released.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from pydantic import BaseModel, Field, JsonValue, field_validator

from kiln_ai.datamodel.basemodel import (
    FilenameString,
    KilnParentedModel,
    KilnParentModel,
)
from kiln_ai.datamodel.code_tool import CodeToolBase
from kiln_ai.datamodel.tool_id import (
    KILN_UNMANAGED_TOOL_ID_PREFIX,
    SKILL_TOOL_ID_PREFIX,
    SYNTHETIC_TOOL_ID_PREFIX,
    ToolId,
)

if TYPE_CHECKING:
    from kiln_ai.datamodel.project import Project

WORLD_LIB_DIRNAME = "lib"
LOCAL_FILES_LAUNCHER = "local_files"


def canonical_json(value: JsonValue) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class SyntheticEnvironment(BaseModel):
    """Which world an eval input runs in, and the launch config for its instance.

    `config` is opaque to Kiln: the world's launcher interprets it (a fixture id for
    file-backed worlds, a seed or task for a gym-style environment). It is part of the
    trace key, so two inputs with different configs never share a generation.
    """

    world_id: str = Field(min_length=1, description="The SyntheticWorld to run in.")
    config: dict[str, JsonValue] = Field(
        default_factory=dict,
        description="Launch configuration passed verbatim to the world's launcher, e.g. {'fixture_id': ...}.",
    )


class SyntheticInstanceConnection(BaseModel):
    """How to reach a hosted instance: an HTTP endpoint or a stdio command.

    `headers` and `env` hold per-instance credentials. They are excluded from
    serialization, so they never land on the trace, in an API response, or in a judge
    prompt; only the in-memory record handed to tools during the run carries them.
    """

    transport: str = Field(
        default="http",
        min_length=1,
        description="'http' for a URL the instance serves (MCP or REST), 'stdio' for a command to spawn, or a launcher-defined name.",
    )
    url: str | None = Field(default=None, description="Address of an HTTP instance.")
    headers: dict[str, str] = Field(
        default_factory=dict,
        exclude=True,
        description="Request headers for an HTTP instance, typically a per-instance bearer token. Never persisted.",
    )
    command: str | None = Field(
        default=None, description="Executable of a stdio instance."
    )
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(
        default_factory=dict,
        exclude=True,
        description="Environment for a stdio instance. Never persisted.",
    )

    def to_sandbox_dict(self) -> dict[str, JsonValue]:
        return {
            "transport": self.transport,
            "url": self.url,
            "headers": dict(self.headers),
            "command": self.command,
            "args": list(self.args),
            "env": dict(self.env),
        }


class SyntheticInstance(BaseModel):
    """One launched instance, recorded on the trace it was generated for.

    Persisted on `TaskRun.synthetic_instance` so graders (including judges added
    later, which reuse the same trace) can find the state the run left behind.
    Exactly what a launcher returns; `path` is local to the machine that ran the eval,
    `connection` is how to reach a hosted instance while it is alive, and `changes` is
    what a launcher records at finalize for graders that outlive the instance.
    """

    instance_id: str = Field(min_length=1)
    world_id: str = Field(min_length=1)
    config: dict[str, JsonValue] = Field(
        default_factory=dict,
        description="The launch config this instance was created from.",
    )
    path: str | None = Field(
        default=None,
        description="Local directory holding this instance's state, for file-backed launchers.",
    )
    connection: SyntheticInstanceConnection | None = Field(
        default=None,
        description="How to reach a hosted instance, for launchers that serve it over the network or as a subprocess.",
    )
    source_path: str | None = Field(
        default=None,
        description="For file-backed launchers: the read-only original the instance was copied from; what readers use once `unchanged` is set.",
    )
    world_lib_path: str | None = Field(
        default=None,
        description="The world's shared lib/ directory, put on the sandbox import path.",
    )
    metadata: dict[str, JsonValue] = Field(
        default_factory=dict,
        description="Facts the launcher reports about the instance, e.g. frozen_time or fixture_id. Scalar entries are exported to tools as KILN_SYNTHETIC_<KEY>.",
    )
    content_version: str | None = Field(
        default=None,
        description="The launcher's identity for the content this instance started from (world code plus fixture bytes, or a framework's world and fixture versions). Part of the trace fingerprint.",
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now().astimezone())
    unchanged: bool = Field(
        default=False,
        description="True once the run was found to have left the instance identical to its source; the copy is released and readers use source_path.",
    )
    changes: dict[str, JsonValue] | None = Field(
        default=None,
        description="What the run changed, as recorded by the launcher at finalize (a changeset, a diff, a summary). Handed to code scorers; the durable record for launchers whose instances are short-lived.",
    )
    valid: bool = Field(
        default=True,
        description="False when the launcher judged the run not transferable: the instance served an unfaithful tool surface, or the run hit gaps in the world. Strict worlds skip grading such runs.",
    )
    invalid_reason: str | None = Field(default=None)

    @property
    def effective_path(self) -> str | None:
        """Where a reader finds this instance's state: the copy, or the source when unchanged."""
        if self.unchanged and self.source_path:
            return self.source_path
        return self.path

    def to_sandbox_dict(self) -> dict[str, JsonValue]:
        """The stdlib-only shape handed to sandbox children and scorers."""
        return {
            "instance_id": self.instance_id,
            "world_id": self.world_id,
            "config": self.config,
            "path": self.effective_path,
            "endpoint": self.connection.url if self.connection else None,
            "connection": self.connection.to_sandbox_dict()
            if self.connection
            else None,
            "source_path": self.source_path,
            "world_lib_path": self.world_lib_path,
            "metadata": self.metadata,
            "content_version": self.content_version,
            "unchanged": self.unchanged,
            "changes": self.changes,
            "valid": self.valid,
            "invalid_reason": self.invalid_reason,
        }


class SyntheticInstanceInfo(BaseModel):
    """The grader-facing view of an instance: identity and reported facts, no locations
    or credentials, and no changeset (it can be large; code scorers get it through the
    sandbox inputs instead).

    `EvalTaskInput` is a FastAPI request body, so paths and connections must not travel
    on it.
    """

    instance_id: str
    world_id: str
    config: dict[str, JsonValue] = Field(default_factory=dict)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)
    content_version: str | None = None
    valid: bool = True
    invalid_reason: str | None = None

    @classmethod
    def from_instance(cls, instance: SyntheticInstance) -> "SyntheticInstanceInfo":
        return cls(
            instance_id=instance.instance_id,
            world_id=instance.world_id,
            config=instance.config,
            metadata=instance.metadata,
            content_version=instance.content_version,
            valid=instance.valid,
            invalid_reason=instance.invalid_reason,
        )


def synthetic_fingerprint(
    world_id: str,
    config: dict[str, JsonValue],
    content_version: str | None,
) -> str:
    """What makes two synthetic generations comparable: same world, config, content.

    Composed into the trace key's variant slot so a trace generated under one config is
    never reused for another, and so a re-engineered world or a regenerated fixture
    regenerates. `content_version` comes from the launcher, before launch.
    """
    payload = "|".join([world_id, canonical_json(config), content_version or ""])
    return "syn2:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


class SyntheticTool(CodeToolBase):
    """A world's Python implementation of one real tool.

    Presents the real tool's function name and schema to the model and runs this code
    instead. Stored under the world, never in the project's code-tool list, so it is
    invisible to run-config pickers; the only way to reach it is through the world
    binding while an instance is active.
    """

    _kiln_filename: ClassVar[str] = "synthetic_tool.kiln"

    replaces_tool_id: ToolId = Field(
        description="The real tool this one plays. Any resolvable tool id: code, MCP, Kiln task, or built-in."
    )

    @field_validator("replaces_tool_id")
    @classmethod
    def _real_tool_only(cls, v: str) -> str:
        for prefix, label in (
            (SYNTHETIC_TOOL_ID_PREFIX, "another synthetic tool"),
            (SKILL_TOOL_ID_PREFIX, "a skill"),
            (KILN_UNMANAGED_TOOL_ID_PREFIX, "an unmanaged tool"),
        ):
            if v.startswith(prefix):
                raise ValueError(
                    f"replaces_tool_id must name a real, registry-resolvable tool, not {label}: {v}"
                )
        return v


class SyntheticWorld(
    KilnParentedModel,
    KilnParentModel,
    parent_of={"tools": SyntheticTool},
):
    """The code that plays a client's tool set, and the launcher that creates its instances."""

    name: FilenameString = Field(description="User-facing display name.")
    description: str | None = Field(default=None)
    launcher: str = Field(
        default=LOCAL_FILES_LAUNCHER,
        min_length=1,
        description="Which launcher creates this world's instances. 'local_files' copies a fixture directory under the world; other launchers are registered by name.",
    )
    launcher_config: dict[str, JsonValue] = Field(
        default_factory=dict,
        description="World-level settings for the launcher (an image, a server address). Opaque to Kiln.",
    )
    strict: bool = Field(
        default=False,
        description="When an instance is active, fail the job if the run config uses a registry-resolved tool this world does not replace (built-ins excepted). Skills and unmanaged tools bypass the registry and are not covered.",
    )
    content_version: str | None = Field(
        default=None,
        description="Author-declared version of the code behind this world. Launchers fold it into the content version they report, so bumping it regenerates the world's traces.",
    )
    replaces_tool_server_id: str | None = Field(
        default=None,
        description="An external tool server (MCP) whose whole tool surface a launched instance serves. While an instance with a connection is active, every tool of that server resolves to the same-named tool on the instance. Per-tool bindings still apply to anything else.",
    )

    def tools(self, readonly: bool = False) -> list[SyntheticTool]:
        return super().tools(readonly=readonly)  # type: ignore

    def world_dir(self) -> Path:
        if self.path is None:
            raise ValueError("World must be saved before accessing its directory")
        return self.path.parent

    def lib_dir(self) -> Path:
        return self.world_dir() / WORLD_LIB_DIRNAME

    def bindings(self, readonly: bool = True) -> dict[str, SyntheticTool]:
        """Real tool id -> the synthetic tool that plays it."""
        result: dict[str, SyntheticTool] = {}
        for tool in self.tools(readonly=readonly):
            if tool.replaces_tool_id in result:
                raise ValueError(
                    f"World '{self.name}' binds {tool.replaces_tool_id} twice "
                    f"(tools {result[tool.replaces_tool_id].id} and {tool.id})"
                )
            result[tool.replaces_tool_id] = tool
        return result

    def binding_for(self, tool_id: str) -> SyntheticTool | None:
        return self.bindings().get(tool_id)

    def replaces_server_of(self, tool_id: str) -> bool:
        """Whether *tool_id* belongs to the tool server this world replaces wholesale."""
        if self.replaces_tool_server_id is None:
            return False
        from kiln_ai.datamodel.tool_id import (
            MCP_LOCAL_TOOL_ID_PREFIX,
            MCP_REMOTE_TOOL_ID_PREFIX,
            mcp_server_and_tool_name_from_id,
        )

        if not tool_id.startswith(
            (MCP_REMOTE_TOOL_ID_PREFIX, MCP_LOCAL_TOOL_ID_PREFIX)
        ):
            return False
        server_id, _ = mcp_server_and_tool_name_from_id(tool_id)
        return server_id == self.replaces_tool_server_id

    def validate_bindings(self, project: "Project") -> list[str]:
        """Check each binding against the real tool it replaces, without any network.

        Raises on a duplicate binding. Returns human-readable warnings for the checks
        that can be made offline: a code tool or Kiln task tool whose function name
        differs from the synthetic tool's, or a code tool whose parameter schema
        differs. MCP tools are never contacted here; their definitions would need a
        live server.
        """
        from kiln_ai.datamodel.code_tool import CodeTool
        from kiln_ai.datamodel.tool_id import (
            CODE_TOOL_ID_PREFIX,
            KILN_TASK_TOOL_ID_PREFIX,
            code_tool_id_from_tool_id,
            kiln_task_server_id_from_tool_id,
        )

        warnings: list[str] = []
        if self.replaces_tool_server_id is not None:
            servers = {s.id for s in project.external_tool_servers(readonly=True)}
            if self.replaces_tool_server_id not in servers:
                warnings.append(
                    f"replaces_tool_server_id {self.replaces_tool_server_id}: external tool server not found in project"
                )
        for real_id, synthetic in self.bindings().items():
            if real_id.startswith(CODE_TOOL_ID_PREFIX):
                real = CodeTool.from_id_and_parent_path(
                    code_tool_id_from_tool_id(real_id), project.path
                )
                if real is None:
                    warnings.append(f"{real_id}: real code tool not found in project")
                    continue
                if real.tool_function_name != synthetic.tool_function_name:
                    warnings.append(
                        f"{real_id}: function name mismatch (real '{real.tool_function_name}', synthetic '{synthetic.tool_function_name}')"
                    )
                if real.parameters_schema != synthetic.parameters_schema:
                    warnings.append(f"{real_id}: parameters schema differs")
            elif real_id.startswith(KILN_TASK_TOOL_ID_PREFIX):
                server_id = kiln_task_server_id_from_tool_id(real_id)
                server = next(
                    (
                        s
                        for s in project.external_tool_servers(readonly=True)
                        if s.id == server_id
                    ),
                    None,
                )
                if server is None:
                    warnings.append(f"{real_id}: Kiln task tool server not found")
                    continue
                real_name = server.properties.get("name")
                if real_name != synthetic.tool_function_name:
                    warnings.append(
                        f"{real_id}: function name mismatch (real '{real_name}', synthetic '{synthetic.tool_function_name}')"
                    )
        return warnings
