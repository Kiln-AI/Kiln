from typing import Union

from kiln_ai.datamodel.tool_id import KilnBuiltInToolId
from kiln_ai.tools.base_tool import KilnTool


class AddTool(KilnTool):
    """
    A concrete tool that adds two numbers together.
    Demonstrates how to use the KilnTool base class.
    """

    def __init__(self):
        parameters_schema = {
            "type": "object",
            "properties": {
                "a": {"type": "number", "description": "The first number to add"},
                "b": {"type": "number", "description": "The second number to add"},
            },
            "required": ["a", "b"],
        }

        super().__init__(
            tool_id=KilnBuiltInToolId.ADD_NUMBERS,
            name="add",
            description="Add two numbers together and return the result",
            parameters_schema=parameters_schema,
        )

    async def run(self, a: Union[int, float], b: Union[int, float]) -> str:
        """Add two numbers and return the result."""
        return str(a + b)


class SubtractTool(KilnTool):
    """
    A concrete tool that subtracts two numbers.
    """

    def __init__(self):
        parameters_schema = {
            "type": "object",
            "properties": {
                "a": {"type": "number", "description": "The first number (minuend)"},
                "b": {
                    "type": "number",
                    "description": "The second number to subtract (subtrahend)",
                },
            },
            "required": ["a", "b"],
        }

        super().__init__(
            tool_id=KilnBuiltInToolId.SUBTRACT_NUMBERS,
            name="subtract",
            description="Subtract the second number from the first number and return the result",
            parameters_schema=parameters_schema,
        )

    async def run(self, a: Union[int, float], b: Union[int, float]) -> str:
        """Subtract b from a and return the result."""
        return str(a - b)


class MultiplyTool(KilnTool):
    """
    A concrete tool that multiplies two numbers together.
    """

    def __init__(self):
        parameters_schema = {
            "type": "object",
            "properties": {
                "a": {"type": "number", "description": "The first number to multiply"},
                "b": {"type": "number", "description": "The second number to multiply"},
            },
            "required": ["a", "b"],
        }

        super().__init__(
            tool_id=KilnBuiltInToolId.MULTIPLY_NUMBERS,
            name="multiply",
            description="Multiply two numbers together and return the result",
            parameters_schema=parameters_schema,
        )

    async def run(self, a: Union[int, float], b: Union[int, float]) -> str:
        """Multiply two numbers and return the result."""
        return str(a * b)


class DivideTool(KilnTool):
    """
    A concrete tool that divides two numbers.
    """

    def __init__(self):
        parameters_schema = {
            "type": "object",
            "properties": {
                "a": {
                    "type": "number",
                    "description": "The dividend (number to be divided)",
                },
                "b": {
                    "type": "number",
                    "description": "The divisor (number to divide by)",
                },
            },
            "required": ["a", "b"],
        }

        super().__init__(
            tool_id=KilnBuiltInToolId.DIVIDE_NUMBERS,
            name="divide",
            description="Divide the first number by the second number and return the result",
            parameters_schema=parameters_schema,
        )

    async def run(self, a: Union[int, float], b: Union[int, float]) -> str:
        """Divide a by b and return the result."""
        if b == 0:
            raise ZeroDivisionError("Cannot divide by zero")
        return str(a / b)
