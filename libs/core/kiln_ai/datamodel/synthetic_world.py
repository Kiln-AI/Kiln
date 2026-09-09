"""Synthetic worlds: a replica of the tool set an agent sees, replayed against synthetic
starting states so evals can read and write without touching a real backend.

Three concepts, three on-disk shapes under a project:

    synthetic_worlds/<id> - <name>/synthetic_world.kiln          SyntheticWorld
        lib/                                                      shared world code
        tools/<id> - <name>/synthetic_tool.kiln + tool.py         SyntheticTool
        fixtures/<id> - <name>/synthetic_fixture.kiln + data/     SyntheticFixture

A **world** is the code that plays a client's tool set: each `SyntheticTool` declares
the real tool id it replaces. A **fixture** is one starting state: opaque data files
plus the timezone-aware "now" they were authored against. An **instance** is a
disposable copy of a fixture that one eval run mutates; it is runtime state, recorded
on the trace as `SyntheticInstance` rather than stored as a project artifact.

Kiln never reads fixture bytes. It copies them, hands the copy's path to the world's
tools and to graders, and decides when the copy can be dropped.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from pydantic import BaseModel, Field, field_validator
from typing_extensions import Self

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
FIXTURE_DATA_DIRNAME = "data"


def _require_tz_aware(v: datetime | None) -> datetime | None:
    """Reject naive datetimes rather than guessing the offset.

    A fixture's "now" is compared against dates baked into its data, so an implicit
    local offset would silently shift every relative query by the author's timezone.
    """
    if v is not None and v.tzinfo is None:
        raise ValueError("frozen_time must be timezone-aware")
    return v


class SyntheticEnvironment(BaseModel):
    """Which world and fixture an eval input runs against, set on `EvalInput`.

    `str` ids rather than `ID_TYPE`: an id-less reference cannot resolve to anything,
    so the None state has no meaning here, and a min_length keeps an empty string
    from slipping through validation.
    """

    world_id: str = Field(min_length=1, description="The SyntheticWorld to run in.")
    fixture_id: str = Field(
        min_length=1, description="The world's SyntheticFixture to start from."
    )
    frozen_time: datetime | None = Field(
        default=None,
        description="Overrides the fixture's frozen_time for this input. Timezone-aware.",
    )

    _tz = field_validator("frozen_time")(_require_tz_aware)


class SyntheticInstance(BaseModel):
    """One run's private copy of a fixture, recorded on the trace it was generated for.

    Persisted on `TaskRun.synthetic_instance` so graders (including judges added
    later, which reuse the same trace) can find the state the run left behind.
    Paths are local to the machine that ran the eval.
    """

    instance_id: str = Field(min_length=1)
    world_id: str = Field(min_length=1)
    fixture_id: str = Field(min_length=1)
    path: str = Field(
        description="Directory holding this instance's copy of the fixture data. Deleted once `unchanged` is set."
    )
    fixture_data_path: str = Field(
        description="The fixture's own data directory, read-only for consumers."
    )
    world_lib_path: str | None = Field(
        default=None,
        description="The world's shared lib/ directory, put on the sandbox import path.",
    )
    frozen_time: datetime | None = Field(
        default=None, description="The clock this instance ran under. Timezone-aware."
    )
    framework_content_hash: str | None = Field(
        default=None,
        description="Hash of the world engine that backed this run, copied from the world.",
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now().astimezone())
    unchanged: bool = Field(
        default=False,
        description="True once the run was found to have left the copy byte-identical to the fixture; the copy is deleted and readers use fixture_data_path.",
    )

    _tz = field_validator("frozen_time")(_require_tz_aware)

    @property
    def effective_path(self) -> str:
        """Where a reader finds this instance's state: the copy, or the fixture when unchanged."""
        return self.fixture_data_path if self.unchanged else self.path

    def to_sandbox_dict(self) -> dict[str, str | bool | None]:
        """The stdlib-only shape handed to sandbox children and scorers."""
        return {
            "instance_id": self.instance_id,
            "world_id": self.world_id,
            "fixture_id": self.fixture_id,
            "path": self.effective_path,
            "fixture_data_path": self.fixture_data_path,
            "world_lib_path": self.world_lib_path,
            "frozen_time": self.frozen_time.isoformat() if self.frozen_time else None,
            "framework_content_hash": self.framework_content_hash,
            "unchanged": self.unchanged,
        }


class SyntheticInstanceInfo(BaseModel):
    """The grader-facing view of an instance: identity and clock, no filesystem paths.

    `EvalTaskInput` is a FastAPI request body, so paths must not travel on it; code-eval
    scorers get the full record through the sandbox inputs instead.
    """

    instance_id: str
    world_id: str
    fixture_id: str
    frozen_time: datetime | None = None
    framework_content_hash: str | None = None

    @classmethod
    def from_instance(cls, instance: SyntheticInstance) -> "SyntheticInstanceInfo":
        return cls(
            instance_id=instance.instance_id,
            world_id=instance.world_id,
            fixture_id=instance.fixture_id,
            frozen_time=instance.frozen_time,
            framework_content_hash=instance.framework_content_hash,
        )


def synthetic_fingerprint(
    world_id: str,
    fixture_id: str,
    frozen_time: datetime | None,
    framework_content_hash: str | None,
) -> str:
    """What makes two synthetic generations comparable: same world, fixture, clock, engine.

    Composed into the trace key's variant slot so a trace generated against one fixture
    is never reused for another, and so a re-engineered world regenerates.
    """
    payload = "|".join(
        [
            world_id,
            fixture_id,
            frozen_time.isoformat() if frozen_time else "",
            framework_content_hash or "",
        ]
    )
    return "syn1:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


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


class SyntheticFixture(KilnParentedModel):
    """A starting state for a world: data files plus the "now" they were authored against.

    Data lives in a sibling `data/` directory and is opaque to Kiln. It is validated when
    an instance is created, not on load, so listing fixtures never touches the files.
    """

    name: FilenameString = Field(description="User-facing display name.")
    description: str | None = Field(default=None)
    frozen_time: datetime | None = Field(
        default=None,
        description="The clock the data was authored against; becomes the instance clock unless the eval input overrides it. Timezone-aware.",
    )

    _tz = field_validator("frozen_time")(_require_tz_aware)

    def data_dir(self) -> Path:
        if self.path is None:
            raise ValueError(
                "Fixture must be saved before accessing its data directory"
            )
        return self.path.parent / FIXTURE_DATA_DIRNAME

    def require_data_dir(self) -> Path:
        """The data directory, checked to exist and hold at least one file."""
        data_dir = self.data_dir()
        if not data_dir.is_dir():
            raise ValueError(
                f"Fixture '{self.name}' has no {FIXTURE_DATA_DIRNAME}/ directory at {data_dir}"
            )
        if not any(p.is_file() for p in data_dir.rglob("*")):
            raise ValueError(
                f"Fixture '{self.name}' has an empty {FIXTURE_DATA_DIRNAME}/ directory at {data_dir}"
            )
        return data_dir

    def resolve_data_file(self, relative_path: str) -> Path:
        """A file inside data/, refusing anything that resolves outside it."""
        if not relative_path or not relative_path.strip():
            raise ValueError("Path cannot be empty")
        base = self.data_dir()
        target = base / relative_path
        try:
            resolved = target.resolve()
            resolved.relative_to(base.resolve())
        except ValueError:
            raise ValueError("Path traversal is not allowed") from None
        return resolved


class SyntheticWorld(
    KilnParentedModel,
    KilnParentModel,
    parent_of={
        "tools": SyntheticTool,
        "fixtures": SyntheticFixture,
    },
):
    """The code that plays a client's tool set, plus the fixtures it can start from."""

    name: FilenameString = Field(description="User-facing display name.")
    description: str | None = Field(default=None)
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

    def fixtures(self, readonly: bool = False) -> list[SyntheticFixture]:
        return super().fixtures(readonly=readonly)  # type: ignore

    def lib_dir(self) -> Path:
        if self.path is None:
            raise ValueError("World must be saved before accessing its lib directory")
        return self.path.parent / WORLD_LIB_DIRNAME

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

    def fixture_by_id(self, fixture_id: str) -> SyntheticFixture | None:
        return SyntheticFixture.from_id_and_parent_path(fixture_id, self.path)

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

    def check_bindings_unique(self) -> Self:
        self.bindings()
        return self
