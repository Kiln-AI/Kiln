import pytest

from kiln_ai.tools.built_in_tools.math_tools import (
    AddTool,
    DivideTool,
    MultiplyTool,
    SubtractTool,
)
from kiln_ai.tools.tool_id import KilnBuiltInToolId
from kiln_ai.tools.tool_registry import tool_from_id


class TestToolRegistry:
    """Test the tool registry functionality."""

    def test_tool_from_id_add_numbers(self):
        """Test that ADD_NUMBERS tool ID returns AddTool instance."""
        tool = tool_from_id(KilnBuiltInToolId.ADD_NUMBERS)

        assert isinstance(tool, AddTool)
        assert tool.id() == KilnBuiltInToolId.ADD_NUMBERS
        assert tool.name() == "add"
        assert "Add two numbers" in tool.description()

    def test_tool_from_id_subtract_numbers(self):
        """Test that SUBTRACT_NUMBERS tool ID returns SubtractTool instance."""
        tool = tool_from_id(KilnBuiltInToolId.SUBTRACT_NUMBERS)

        assert isinstance(tool, SubtractTool)
        assert tool.id() == KilnBuiltInToolId.SUBTRACT_NUMBERS
        assert tool.name() == "subtract"

    def test_tool_from_id_multiply_numbers(self):
        """Test that MULTIPLY_NUMBERS tool ID returns MultiplyTool instance."""
        tool = tool_from_id(KilnBuiltInToolId.MULTIPLY_NUMBERS)

        assert isinstance(tool, MultiplyTool)
        assert tool.id() == KilnBuiltInToolId.MULTIPLY_NUMBERS
        assert tool.name() == "multiply"

    def test_tool_from_id_divide_numbers(self):
        """Test that DIVIDE_NUMBERS tool ID returns DivideTool instance."""
        tool = tool_from_id(KilnBuiltInToolId.DIVIDE_NUMBERS)

        assert isinstance(tool, DivideTool)
        assert tool.id() == KilnBuiltInToolId.DIVIDE_NUMBERS
        assert tool.name() == "divide"

    def test_tool_from_id_with_string_values(self):
        """Test that tool_from_id works with string values of enum members."""
        tool = tool_from_id("kiln_tool::add_numbers")

        assert isinstance(tool, AddTool)
        assert tool.id() == KilnBuiltInToolId.ADD_NUMBERS

    def test_tool_from_id_invalid_tool_id(self):
        """Test that invalid tool ID raises ValueError."""
        with pytest.raises(
            ValueError, match="Tool ID invalid_tool_id not found in tool registry"
        ):
            tool_from_id("invalid_tool_id")

    def test_tool_from_id_empty_string(self):
        """Test that empty string tool ID raises ValueError."""
        with pytest.raises(ValueError, match="Tool ID  not found in tool registry"):
            tool_from_id("")

    def test_all_built_in_tools_are_registered(self):
        """Test that all KilnBuiltInToolId enum members are handled by the registry."""
        for tool_id in KilnBuiltInToolId:
            # This should not raise an exception
            tool = tool_from_id(tool_id.value)
            assert tool is not None

    def test_registry_returns_new_instances(self):
        """Test that registry returns new instances each time (not singletons)."""
        tool1 = tool_from_id(KilnBuiltInToolId.ADD_NUMBERS)
        tool2 = tool_from_id(KilnBuiltInToolId.ADD_NUMBERS)

        assert tool1 is not tool2  # Different instances
        assert type(tool1) is type(tool2)  # Same type
        assert tool1.id() == tool2.id()  # Same id
