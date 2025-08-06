import pytest

from kiln_ai.tools.built_in_tools.math_tools import (
    AddTool,
    DivideTool,
    MultiplyTool,
    SubtractTool,
)
from kiln_ai.tools.tool_id import KilnBuiltInToolId


class TestAddTool:
    """Test the AddTool class."""

    def test_init(self):
        """Test AddTool initialization."""
        tool = AddTool()
        assert tool.id() == KilnBuiltInToolId.ADD_NUMBERS
        assert tool.name() == "add"
        assert tool.description() == "Add two numbers together and return the result"

    def test_toolcall_definition(self):
        """Test AddTool toolcall definition structure."""
        tool = AddTool()
        definition = tool.toolcall_definition()

        assert definition["type"] == "function"
        assert definition["function"]["name"] == "add"
        assert (
            definition["function"]["description"]
            == "Add two numbers together and return the result"
        )
        assert "properties" in definition["function"]["parameters"]
        assert "a" in definition["function"]["parameters"]["properties"]
        assert "b" in definition["function"]["parameters"]["properties"]

    @pytest.mark.parametrize(
        "a, b, expected",
        [
            (1, 2, "3"),
            (0, 0, "0"),
            (-1, 1, "0"),
            (2.5, 3.5, "6.0"),
            (-2.5, -3.5, "-6.0"),
            (100, 200, "300"),
        ],
    )
    def test_run_various_inputs(self, a, b, expected):
        """Test AddTool run method with various inputs."""
        tool = AddTool()
        result = tool.run(a=a, b=b)
        assert result == expected


class TestSubtractTool:
    """Test the SubtractTool class."""

    def test_init(self):
        """Test SubtractTool initialization."""
        tool = SubtractTool()
        assert tool.id() == KilnBuiltInToolId.SUBTRACT_NUMBERS
        assert tool.name() == "subtract"
        assert (
            tool.description()
            == "Subtract the second number from the first number and return the result"
        )

    def test_toolcall_definition(self):
        """Test SubtractTool toolcall definition structure."""
        tool = SubtractTool()
        definition = tool.toolcall_definition()

        assert definition["type"] == "function"
        assert definition["function"]["name"] == "subtract"
        assert (
            definition["function"]["description"]
            == "Subtract the second number from the first number and return the result"
        )
        assert "properties" in definition["function"]["parameters"]
        assert "a" in definition["function"]["parameters"]["properties"]
        assert "b" in definition["function"]["parameters"]["properties"]

    @pytest.mark.parametrize(
        "a, b, expected",
        [
            (5, 3, "2"),
            (0, 0, "0"),
            (1, -1, "2"),
            (5.5, 2.5, "3.0"),
            (-2.5, -3.5, "1.0"),
            (100, 200, "-100"),
        ],
    )
    def test_run_various_inputs(self, a, b, expected):
        """Test SubtractTool run method with various inputs."""
        tool = SubtractTool()
        result = tool.run(a=a, b=b)
        assert result == expected


class TestMultiplyTool:
    """Test the MultiplyTool class."""

    def test_init(self):
        """Test MultiplyTool initialization."""
        tool = MultiplyTool()
        assert tool.id() == KilnBuiltInToolId.MULTIPLY_NUMBERS
        assert tool.name() == "multiply"
        assert (
            tool.description() == "Multiply two numbers together and return the result"
        )

    def test_toolcall_definition(self):
        """Test MultiplyTool toolcall definition structure."""
        tool = MultiplyTool()
        definition = tool.toolcall_definition()

        assert definition["type"] == "function"
        assert definition["function"]["name"] == "multiply"
        assert (
            definition["function"]["description"]
            == "Multiply two numbers together and return the result"
        )
        assert "properties" in definition["function"]["parameters"]
        assert "a" in definition["function"]["parameters"]["properties"]
        assert "b" in definition["function"]["parameters"]["properties"]

    @pytest.mark.parametrize(
        "a, b, expected",
        [
            (2, 3, "6"),
            (0, 5, "0"),
            (-2, 3, "-6"),
            (2.5, 4, "10.0"),
            (-2.5, -4, "10.0"),
            (1, 1, "1"),
        ],
    )
    def test_run_various_inputs(self, a, b, expected):
        """Test MultiplyTool run method with various inputs."""
        tool = MultiplyTool()
        result = tool.run(a=a, b=b)
        assert result == expected


class TestDivideTool:
    """Test the DivideTool class."""

    def test_init(self):
        """Test DivideTool initialization."""
        tool = DivideTool()
        assert tool.id() == KilnBuiltInToolId.DIVIDE_NUMBERS
        assert tool.name() == "divide"
        assert (
            tool.description()
            == "Divide the first number by the second number and return the result"
        )

    def test_toolcall_definition(self):
        """Test DivideTool toolcall definition structure."""
        tool = DivideTool()
        definition = tool.toolcall_definition()

        assert definition["type"] == "function"
        assert definition["function"]["name"] == "divide"
        assert (
            definition["function"]["description"]
            == "Divide the first number by the second number and return the result"
        )
        assert "properties" in definition["function"]["parameters"]
        assert "a" in definition["function"]["parameters"]["properties"]
        assert "b" in definition["function"]["parameters"]["properties"]

    @pytest.mark.parametrize(
        "a, b, expected",
        [
            (6, 2, "3.0"),
            (1, 1, "1.0"),
            (-6, 2, "-3.0"),
            (7.5, 2.5, "3.0"),
            (-10, -2, "5.0"),
            (0, 5, "0.0"),
        ],
    )
    def test_run_various_inputs(self, a, b, expected):
        """Test DivideTool run method with various inputs."""
        tool = DivideTool()
        result = tool.run(a=a, b=b)
        assert result == expected

    def test_divide_by_zero(self):
        """Test that division by zero raises ZeroDivisionError."""
        tool = DivideTool()
        with pytest.raises(ZeroDivisionError, match="Cannot divide by zero"):
            tool.run(a=5, b=0)

    def test_divide_zero_by_zero(self):
        """Test that zero divided by zero raises ZeroDivisionError."""
        tool = DivideTool()
        with pytest.raises(ZeroDivisionError, match="Cannot divide by zero"):
            tool.run(a=0, b=0)
