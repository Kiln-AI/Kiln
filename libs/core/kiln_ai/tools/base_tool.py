from abc import ABC, abstractmethod
from typing import Any, Dict

from kiln_ai.datamodel.json_schema import validate_schema_dict
from kiln_ai.datamodel.tool_id import KilnBuiltInToolId, ToolId


class KilnToolInterface(ABC):
    """
    Abstract interface defining the core API that all Kiln tools must implement.
    This ensures consistency across all tool implementations.
    """

    @abstractmethod
    async def run(self, **kwargs) -> Any:
        """Execute the tool with the given parameters."""
        pass

    @abstractmethod
    async def toolcall_definition(self) -> Dict[str, Any]:
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

    async def toolcall_definition(self) -> Dict[str, Any]:
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
    async def run(self, **kwargs) -> str:
        """Subclasses must implement the actual tool logic."""
        pass
