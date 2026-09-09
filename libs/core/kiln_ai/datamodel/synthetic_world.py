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
the launcher, hands the instance to tools and graders, keys traces by the config, and
decides when an instance can be released.
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


class SyntheticInstance(BaseModel):
    """One launched instance, recorded on the trace it was generated for.

    Persisted on `TaskRun.synthetic_instance` so graders (including judges added
    later, which reuse the same trace) can find the state the run left behind.
    Exactly what a launcher returns; `path` is local to the machine that ran the eval.
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
    endpoint: str | None = Field(
        default=None,
        description="Address of a hosted instance, for launchers that serve it over the network.",
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
    framework_content_hash: str | None = Field(
        default=None,
        description="Hash of the world engine that backed this run, copied from the world.",
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now().astimezone())
    unchanged: bool = Field(
        default=False,
        description="True once the run was found to have left the instance identical to its source; the copy is released and readers use source_path.",
    )

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
            "endpoint": self.endpoint,
            "source_path": self.source_path,
            "world_lib_path": self.world_lib_path,
            "metadata": self.metadata,
            "framework_content_hash": self.framework_content_hash,
            "unchanged": self.unchanged,
        }


class SyntheticInstanceInfo(BaseModel):
    """The grader-facing view of an instance: identity and reported facts, no locations.

    `EvalTaskInput` is a FastAPI request body, so paths and endpoints must not travel
    on it; code-eval scorers get the full record through the sandbox inputs instead.
    """

    instance_id: str
    world_id: str
    config: dict[str, JsonValue] = Field(default_factory=dict)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)
    framework_content_hash: str | None = None

    @classmethod
    def from_instance(cls, instance: SyntheticInstance) -> "SyntheticInstanceInfo":
        return cls(
            instance_id=instance.instance_id,
            world_id=instance.world_id,
            config=instance.config,
            metadata=instance.metadata,
            framework_content_hash=instance.framework_content_hash,
        )


def synthetic_fingerprint(
    world_id: str,
    config: dict[str, JsonValue],
    framework_content_hash: str | None,
) -> str:
    """What makes two synthetic generations comparable: same world, config, engine.

    Composed into the trace key's variant slot so a trace generated under one config is
    never reused for another, and so a re-engineered world regenerates.
    """
    payload = "|".join([world_id, canonical_json(config), framework_content_hash or ""])
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
    framework_content_hash: str | None = Field(
        default=None,
        description="Opaque hash of the engine code behind this world. Part of the trace fingerprint, so re-engineering the world regenerates its traces.",
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
