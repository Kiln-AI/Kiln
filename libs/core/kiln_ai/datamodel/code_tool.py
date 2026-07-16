"""CodeTool data model — a user-authored Python function stored as a project artifact."""

import ast
import re
from typing import Any

from pydantic import Field, field_validator, model_validator
from typing_extensions import Self

from kiln_ai.datamodel.basemodel import FilenameString, KilnParentedModel
from kiln_ai.datamodel.json_schema import validate_schema_dict
from kiln_ai.datamodel.provenance import KilnArtifactProvenance
from kiln_ai.datamodel.tool_id import (
    KILN_UNMANAGED_TOOL_ID_PREFIX,
    SKILL_TOOL_ID_PREFIX,
    ToolId,
    build_code_tool_id,
)

_FUNCTION_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class CodeTool(KilnParentedModel):
    """A user-authored Python function that runs as a tool inside the agent harness.

    Functional content (code, schema, allowlist, etc.) is immutable post-create
    — the API enforces this; changing code means cloning into a new tool.
    """

    # Editable metadata
    name: FilenameString = Field(description="User-facing display name.")
    description: str | None = Field(
        default=None,
        description="User-facing notes shown in the UI. Not shown to models.",
    )
    is_archived: bool = Field(
        default=False,
        description="Archived tools are hidden from pickers but still resolve if referenced.",
    )
    provenance: KilnArtifactProvenance | None = Field(
        default=None,
        description="Why this artifact exists and what it was derived from.",
    )

    # Functional content — immutable post-create (enforced at the API layer)
    tool_function_name: str = Field(
        description="The function name exposed to the model. Snake_case identifier."
    )
    tool_description: str = Field(
        min_length=1,
        description="Shown to agents as the tool description.",
    )
    parameters_schema: dict[str, Any] = Field(
        description="JSON Schema for the tool's parameters. Root must be type: object.",
    )
    code: str = Field(
        description="Inline Python source. Validated for syntax and entry-point presence.",
    )
    timeout_seconds: int = Field(
        default=60,
        ge=1,
        description="Wall-clock timeout for one invocation, including nested tool calls.",
    )
    tool_allowlist: list[ToolId] = Field(
        default_factory=list,
        description="Explicit per-tool allowlist of tools this code tool may call.",
    )

    @field_validator("tool_function_name")
    @classmethod
    def validate_function_name(cls, v: str) -> str:
        if not _FUNCTION_NAME_RE.fullmatch(v):
            raise ValueError(
                f"tool_function_name must match ^[a-z][a-z0-9_]{{0,63}}$, got: '{v}'"
            )
        return v

    @model_validator(mode="after")
    def validate_parameters_schema(self) -> Self:
        validate_schema_dict(self.parameters_schema, require_object=True)
        return self

    @model_validator(mode="after")
    def validate_code(self) -> Self:
        code_bytes = self.code.encode("utf-8")
        if len(code_bytes) > 64 * 1024:
            raise ValueError(
                f"Code is too large ({len(code_bytes)} bytes). Maximum size is 64KB."
            )

        try:
            compile(self.code, "<code_tool>", "exec")
        except SyntaxError as e:
            raise ValueError(f"Code has a syntax error: {e}") from e

        tree = ast.parse(self.code)
        has_run_fn = any(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "run"
            for node in ast.iter_child_nodes(tree)
        )
        if not has_run_fn:
            raise ValueError(
                "Code must define a module-level 'run' function (def run(...) or async def run(...))."
            )

        return self

    @model_validator(mode="after")
    def validate_allowlist(self) -> Self:
        seen: set[str] = set()
        for tool_id in self.tool_allowlist:
            if tool_id.startswith(SKILL_TOOL_ID_PREFIX):
                raise ValueError(
                    f"Skill tool IDs cannot be used in tool_allowlist: {tool_id}. "
                    "Skills are adapter-resolved and not callable from code tools."
                )
            if tool_id.startswith(KILN_UNMANAGED_TOOL_ID_PREFIX):
                raise ValueError(
                    f"Unmanaged tool IDs cannot be used in tool_allowlist: {tool_id}. "
                    "Unmanaged tools are SDK-injected and not resolvable by the registry."
                )
            if tool_id in seen:
                raise ValueError(f"Duplicate tool ID in tool_allowlist: {tool_id}")
            seen.add(tool_id)

        if self.id is not None:
            self_tool_id = build_code_tool_id(self.id)
            if self_tool_id in seen:
                raise ValueError(
                    "A code tool cannot reference itself in tool_allowlist."
                )

        return self
