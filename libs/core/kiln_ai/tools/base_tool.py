from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, TypedDict

from pydantic import BaseModel

from kiln_ai.datamodel.json_schema import validate_schema_dict
from kiln_ai.datamodel.tool_id import KilnBuiltInToolId, ToolId


class ToolFunction(TypedDict):
    """Typed dict for the function definition within a tool call definition."""

    name: str
    description: str
    parameters: Dict[str, Any]


class ToolCallDefinition(TypedDict):
    """Typed dict for OpenAI-compatible tool call definitions."""

    type: str  # Must be "function"
    function: ToolFunction


@dataclass
class ToolCallContext:
    """Context passed to tools when they are called, containing information from the calling task."""

    """Used for Kiln Tasks as Tools, to know if the tool call should save the task run it invoked to that task's Dataset."""
    allow_saving: bool = True


class ToolCallResult(BaseModel):
    output: str


class KilnToolInterface(ABC):
    """
    Abstract interface defining the core API that all Kiln tools must implement.
    This ensures consistency across all tool implementations.
    """

    @abstractmethod
    async def run(
        self, context: ToolCallContext | None = None, **kwargs
    ) -> ToolCallResult:
        """Execute the tool with the given parameters and calling context if provided."""
        pass

    @abstractmethod
    async def toolcall_definition(self) -> ToolCallDefinition:
        """Return the OpenAI-compatible tool definition for this tool."""
        pass

    @abstractmethod
    async def id(self) -> ToolId:
        """Return a unique identifier for this tool."""
        pass

    @abstractmethod
    async def name(self) -> str:
        """Return the tool name (function name) of this tool."""
        pass

    @abstractmethod
    async def description(self) -> str:
        """Return a description of what this tool does."""
        pass


class KilnTool(KilnToolInterface):
    """
    Base helper class that provides common functionality for tool implementations.
    Subclasses only need to implement run() and provide tool configuration.
    """

    def __init__(
        self,
        tool_id: KilnBuiltInToolId,
        name: str,
        description: str,
        parameters_schema: Dict[str, Any],
    ):
        self._id = tool_id
        self._name = name
        self._description = description
        validate_schema_dict(parameters_schema)
        self._parameters_schema = parameters_schema

    async def id(self) -> KilnBuiltInToolId:
        return self._id

    async def name(self) -> str:
        return self._name

    async def description(self) -> str:
        return self._description

    async def toolcall_definition(self) -> ToolCallDefinition:
        """Generate OpenAI-compatible tool definition."""
        return {
            "type": "function",
            "function": {
                "name": await self.name(),
                "description": await self.description(),
                "parameters": self._parameters_schema,
            },
        }

    @abstractmethod
    async def run(
        self, context: ToolCallContext | None = None, **kwargs
    ) -> ToolCallResult:
        """Subclasses must implement the actual tool logic."""
        pass
