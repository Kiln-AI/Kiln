from typing import Any, Dict

from kiln_ai.datamodel.tool_id import (
    ToolId,
    client_tool_name_from_id,
)
from kiln_ai.tools.base_tool import (
    KilnToolInterface,
    ToolCallContext,
    ToolCallDefinition,
    ToolCallResult,
)


class ClientToolCallRequired(Exception):
    """Raised when a tool requires client-side execution.

    The remote backend catches this and emits a client-tool-call SSE event
    so the proxy can execute the tool locally and send back the result.
    """

    def __init__(self, tool_call_id: str, tool_name: str, arguments: dict[str, Any]):
        self.tool_call_id = tool_call_id
        self.tool_name = tool_name
        self.arguments = arguments
        super().__init__(f"Client tool '{tool_name}' requires client-side execution")


class ClientToolPlaceholder(KilnToolInterface):
    """A tool placeholder that provides a schema for LLM function calling
    but raises ClientToolCallRequired when executed.

    Used for tools that must run on the client (e.g., reading local files).
    The hosted backend includes these in the LLM's tool list so the model
    can decide to call them, but execution is deferred to the client.
    """

    def __init__(
        self,
        tool_id: str,
        name: str,
        description: str,
        parameters_schema: Dict[str, Any],
    ):
        self._tool_id = tool_id
        self._name = name
        self._description = description
        self._parameters_schema = parameters_schema

    async def id(self) -> ToolId:
        return self._tool_id

    async def name(self) -> str:
        return self._name

    async def description(self) -> str:
        return self._description

    async def toolcall_definition(self) -> ToolCallDefinition:
        return {
            "type": "function",
            "function": {
                "name": self._name,
                "description": self._description,
                "parameters": self._parameters_schema,
            },
        }

    async def run(
        self, context: ToolCallContext | None = None, **kwargs: Any
    ) -> ToolCallResult:
        raise ClientToolCallRequired(
            tool_call_id="",
            tool_name=self._name,
            arguments=dict(kwargs),
        )


# Registry of known client tool definitions.
# The hosted backend uses these schemas so the LLM knows about the tools.
# Execution happens on the client side.
_CLIENT_TOOL_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "read_task_run": {
        "description": "Read a task run from the user's local Kiln project. Returns the task run data as JSON.",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The file path to the task_run.kiln file on the user's machine",
                },
            },
            "required": ["path"],
        },
    },
}


def client_tool_from_id(tool_id: str) -> ClientToolPlaceholder:
    """Create a ClientToolPlaceholder from a client tool ID."""
    tool_name = client_tool_name_from_id(tool_id)
    definition = _CLIENT_TOOL_DEFINITIONS.get(tool_name)
    if definition is None:
        raise ValueError(
            f"Unknown client tool: {tool_name}. "
            f"Known client tools: {list(_CLIENT_TOOL_DEFINITIONS.keys())}"
        )
    return ClientToolPlaceholder(
        tool_id=tool_id,
        name=tool_name,
        description=definition["description"],
        parameters_schema=definition["parameters_schema"],
    )
