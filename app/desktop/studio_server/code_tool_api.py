"""Code Tool API — CRUD + transient test endpoint for user-authored Python code tools."""

import json
import logging
from datetime import datetime
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException, Path
from kiln_ai.adapters.eval.v2_eval_code_eval import has_add_code_trust
from kiln_ai.datamodel.code_tool import CodeTool
from kiln_ai.datamodel.json_schema import validate_schema_with_value_error
from kiln_ai.datamodel.tool_id import ToolId
from kiln_ai.run_context import (
    clear_agent_run_id,
    generate_agent_run_id,
    set_agent_run_id,
)
from kiln_ai.tools.base_tool import ToolCallContext
from kiln_ai.tools.code_tool import ChildOutcome, PythonCodeTool, ToolCallLogEntry
from kiln_ai.tools.mcp_session_manager import MCPSessionManager
from kiln_server.project_api import project_from_id
from kiln_server.utils.agent_checks.policy import (
    ALLOW_AGENT,
    DENY_AGENT,
    agent_policy_require_approval,
)
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError as PydanticValidationError,
)

logger = logging.getLogger(__name__)


class CodeToolCreateRequest(BaseModel):
    name: str = Field(description="User-facing display name.")
    description: str | None = Field(
        default=None, description="User-facing notes shown in the UI."
    )
    tool_function_name: str = Field(
        description="The function name exposed to the model."
    )
    tool_description: str = Field(
        min_length=1, description="Shown to agents as the tool description."
    )
    parameters_schema: dict[str, Any] = Field(
        description="JSON Schema for the tool's parameters."
    )
    code: str = Field(description="Inline Python source.")
    timeout_seconds: int = Field(default=60, ge=1, description="Wall-clock timeout.")
    tool_allowlist: list[ToolId] = Field(
        default_factory=list, description="Tools this code tool may call."
    )


class CodeToolResponse(BaseModel):
    id: str | None = None
    name: str
    description: str | None = None
    is_archived: bool = False
    tool_function_name: str
    tool_description: str
    parameters_schema: dict[str, Any]
    code: str
    timeout_seconds: int
    tool_allowlist: list[ToolId] = Field(default_factory=list)
    created_at: datetime | None = None
    created_by: str | None = None


class CodeToolCreateResponse(BaseModel):
    id: str | None = None
    name: str | None = None
    description: str | None = None
    is_archived: bool = False
    tool_function_name: str | None = None
    tool_description: str | None = None
    parameters_schema: dict[str, Any] | None = None
    code: str | None = None
    timeout_seconds: int | None = None
    tool_allowlist: list[ToolId] = Field(default_factory=list)
    created_at: datetime | None = None
    created_by: str | None = None
    not_trusted: bool = False


class CodeToolUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, description="User-facing display name.")
    description: str | None = Field(
        default=None, description="User-facing notes shown in the UI."
    )


class CodeToolArchiveRequest(BaseModel):
    archived: bool = Field(description="Whether to archive or unarchive the tool.")


class TestCodeToolRequest(BaseModel):
    tool_function_name: str
    tool_description: str = "test"
    parameters_schema: dict[str, Any]
    code: str
    timeout_seconds: int = 60
    tool_allowlist: list[ToolId] = Field(default_factory=list)
    params: dict[str, Any] = Field(description="Invocation arguments for the test.")


class ToolCallLogEntryResponse(BaseModel):
    tool_name: str
    arguments: dict[str, Any]
    output_preview: str
    is_error: bool
    duration_ms: int


class TestCodeToolResponse(BaseModel):
    result: str | None = None
    error: str | None = None
    traceback: str | None = None
    not_trusted: bool = False
    stdout: str = ""
    stderr: str = ""
    tool_call_log: list[ToolCallLogEntryResponse] = Field(default_factory=list)
    duration_ms: int = 0


def _code_tool_from_id(project_id: str, code_tool_id: str) -> CodeTool:
    project = project_from_id(project_id)
    code_tool = CodeTool.from_id_and_parent_path(code_tool_id, project.path)
    if code_tool is None:
        raise HTTPException(status_code=404, detail="Code tool not found")
    return code_tool


def _code_tool_to_response(ct: CodeTool) -> CodeToolResponse:
    return CodeToolResponse(
        id=ct.id,
        name=ct.name,
        description=ct.description,
        is_archived=ct.is_archived,
        tool_function_name=ct.tool_function_name,
        tool_description=ct.tool_description,
        parameters_schema=ct.parameters_schema,
        code=ct.code,
        timeout_seconds=ct.timeout_seconds,
        tool_allowlist=ct.tool_allowlist,
        created_at=ct.created_at,
        created_by=ct.created_by,
    )


def _outcome_to_test_response(
    outcome: ChildOutcome,
    tool_call_log: list[ToolCallLogEntry],
) -> TestCodeToolResponse:
    log_entries = [
        ToolCallLogEntryResponse(
            tool_name=entry.tool_name,
            arguments=entry.arguments,
            output_preview=entry.output_preview,
            is_error=entry.is_error,
            duration_ms=entry.duration_ms,
        )
        for entry in tool_call_log
    ]

    if outcome.ok is not None:
        return TestCodeToolResponse(
            result=outcome.ok,
            stdout=outcome.stdout,
            stderr=outcome.stderr,
            tool_call_log=log_entries,
            duration_ms=outcome.duration_ms,
        )

    error_msg = outcome.error
    if outcome.timed_out:
        error_msg = "Code tool timed out"
    elif outcome.crashed:
        error_msg = f"Code tool crashed (exit code {outcome.exit_code})"

    return TestCodeToolResponse(
        error=error_msg,
        traceback=outcome.traceback_str,
        stdout=outcome.stdout,
        stderr=outcome.stderr,
        tool_call_log=log_entries,
        duration_ms=outcome.duration_ms,
    )


def connect_code_tool_api(app: FastAPI):
    @app.post(
        "/api/projects/{project_id}/code_tools",
        summary="Create Code Tool",
        tags=["Code Tools"],
        openapi_extra=agent_policy_require_approval(
            "Allow agent to create and save a code tool (Python that runs on your machine)?"
        ),
    )
    async def create_code_tool(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        request: CodeToolCreateRequest,
    ) -> CodeToolCreateResponse:
        project = project_from_id(project_id)

        if not has_add_code_trust(str(project.path)):
            return CodeToolCreateResponse(not_trusted=True)

        existing = project.code_tools(readonly=True)
        for ct in existing:
            if (
                not ct.is_archived
                and ct.tool_function_name == request.tool_function_name
            ):
                raise HTTPException(
                    status_code=400,
                    detail=f"A non-archived code tool with function name '{request.tool_function_name}' already exists.",
                )

        try:
            code_tool = CodeTool(
                name=request.name,
                description=request.description,
                tool_function_name=request.tool_function_name,
                tool_description=request.tool_description,
                parameters_schema=request.parameters_schema,
                code=request.code,
                timeout_seconds=request.timeout_seconds,
                tool_allowlist=request.tool_allowlist,
                parent=project,
            )
        except (ValueError, PydanticValidationError) as e:
            raise HTTPException(status_code=400, detail=str(e))

        code_tool.save_to_file()
        return CodeToolCreateResponse(**_code_tool_to_response(code_tool).model_dump())

    @app.post(
        "/api/projects/{project_id}/test_code_tool",
        summary="Test Code Tool",
        tags=["Code Tools"],
        openapi_extra=agent_policy_require_approval(
            "Allow agent to run Python code on your machine? It may call your tools, with side effects."
        ),
    )
    async def test_code_tool(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        request: TestCodeToolRequest,
    ) -> TestCodeToolResponse:
        project = project_from_id(project_id)

        try:
            transient_tool = CodeTool(
                name="test_run",
                tool_function_name=request.tool_function_name,
                tool_description=request.tool_description,
                parameters_schema=request.parameters_schema,
                code=request.code,
                timeout_seconds=request.timeout_seconds,
                tool_allowlist=request.tool_allowlist,
                parent=project,
            )
        except (ValueError, PydanticValidationError) as e:
            raise HTTPException(status_code=400, detail=str(e))

        if not has_add_code_trust(str(project.path)):
            return TestCodeToolResponse(not_trusted=True)

        schema_str = json.dumps(request.parameters_schema, ensure_ascii=False)
        try:
            validate_schema_with_value_error(
                request.params,
                schema_str,
                "Test params do not match the parameters_schema.",
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        tool_call_log: list[ToolCallLogEntry] = []
        run_id = generate_agent_run_id()
        set_agent_run_id(run_id)
        try:
            tool = PythonCodeTool(
                transient_tool,
                project,
                task=None,
                tool_call_recorder=tool_call_log.append,
            )
            outcome = await tool._invoke(
                ToolCallContext(allow_saving=False), request.params
            )
            return _outcome_to_test_response(outcome, tool_call_log)
        finally:
            try:
                await MCPSessionManager.shared().cleanup_session(run_id)
            finally:
                clear_agent_run_id()

    @app.get(
        "/api/projects/{project_id}/code_tools",
        summary="List Code Tools",
        tags=["Code Tools"],
        openapi_extra=ALLOW_AGENT,
    )
    async def list_code_tools(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
    ) -> list[CodeToolResponse]:
        project = project_from_id(project_id)
        tools = project.code_tools(readonly=True)
        tools.sort(key=lambda ct: (ct.is_archived, ct.created_at or datetime.min))
        return [_code_tool_to_response(ct) for ct in tools]

    @app.get(
        "/api/projects/{project_id}/code_tools/{code_tool_id}",
        summary="Get Code Tool",
        tags=["Code Tools"],
        openapi_extra=ALLOW_AGENT,
    )
    async def get_code_tool(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        code_tool_id: Annotated[
            str, Path(description="The unique identifier of the code tool.")
        ],
    ) -> CodeToolResponse:
        ct = _code_tool_from_id(project_id, code_tool_id)
        return _code_tool_to_response(ct)

    @app.patch(
        "/api/projects/{project_id}/code_tools/{code_tool_id}",
        summary="Update Code Tool Metadata",
        tags=["Code Tools"],
        openapi_extra=ALLOW_AGENT,
    )
    async def update_code_tool(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        code_tool_id: Annotated[
            str, Path(description="The unique identifier of the code tool.")
        ],
        updates: CodeToolUpdateRequest,
    ) -> CodeToolResponse:
        ct = _code_tool_from_id(project_id, code_tool_id)

        update_fields = updates.model_dump(exclude_unset=True)
        if not update_fields:
            return _code_tool_to_response(ct)

        merged = ct.model_dump()
        merged.update(update_fields)
        updated = CodeTool.model_validate(merged)
        updated.path = ct.path
        updated.save_to_file()
        return _code_tool_to_response(updated)

    @app.post(
        "/api/projects/{project_id}/code_tools/{code_tool_id}/archive",
        summary="Archive/Unarchive Code Tool",
        tags=["Code Tools"],
        openapi_extra=ALLOW_AGENT,
    )
    async def archive_code_tool(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        code_tool_id: Annotated[
            str, Path(description="The unique identifier of the code tool.")
        ],
        request: CodeToolArchiveRequest,
    ) -> CodeToolResponse:
        ct = _code_tool_from_id(project_id, code_tool_id)
        ct.is_archived = request.archived
        ct.save_to_file()
        return _code_tool_to_response(ct)

    @app.delete(
        "/api/projects/{project_id}/code_tools/{code_tool_id}",
        summary="Delete Code Tool",
        tags=["Code Tools"],
        openapi_extra=DENY_AGENT,
    )
    async def delete_code_tool(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        code_tool_id: Annotated[
            str, Path(description="The unique identifier of the code tool.")
        ],
    ) -> dict[str, str]:
        ct = _code_tool_from_id(project_id, code_tool_id)
        ct.delete()
        return {"status": "deleted"}
