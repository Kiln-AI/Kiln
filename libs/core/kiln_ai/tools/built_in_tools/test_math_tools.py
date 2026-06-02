import json

import pytest

from kiln_ai.datamodel.tool_id import KilnBuiltInToolId
from kiln_ai.tools.built_in_tools.math_tools import (
    AddTool,
    CalculateTool,
    DivideTool,
    MultiplyTool,
    SubtractTool,
)


class TestAddTool:
    """Test the AddTool class."""

    async def test_init(self):
        """Test AddTool initialization."""
        tool = AddTool()
        assert await tool.id() == KilnBuiltInToolId.ADD_NUMBERS
        assert await tool.name() == "add"
        assert (
            await tool.description() == "Add two numbers together and return the result"
        )

    async def test_toolcall_definition(self):
        """Test AddTool toolcall definition structure."""
        tool = AddTool()
        definition = await tool.toolcall_definition()

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
    async def test_run_various_inputs(self, a, b, expected):
        """Test AddTool run method with various inputs."""
        tool = AddTool()
        result = await tool.run(a=a, b=b)
        assert result.output == expected


class TestSubtractTool:
    """Test the SubtractTool class."""

    async def test_init(self):
        """Test SubtractTool initialization."""
        tool = SubtractTool()
        assert await tool.id() == KilnBuiltInToolId.SUBTRACT_NUMBERS
        assert await tool.name() == "subtract"
        assert (
            await tool.description()
            == "Subtract the second number from the first number and return the result"
        )

    async def test_toolcall_definition(self):
        """Test SubtractTool toolcall definition structure."""
        tool = SubtractTool()
        definition = await tool.toolcall_definition()

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
    async def test_run_various_inputs(self, a, b, expected):
        """Test SubtractTool run method with various inputs."""
        tool = SubtractTool()
        result = await tool.run(a=a, b=b)
        assert result.output == expected


class TestMultiplyTool:
    """Test the MultiplyTool class."""

    async def test_init(self):
        """Test MultiplyTool initialization."""
        tool = MultiplyTool()
        assert await tool.id() == KilnBuiltInToolId.MULTIPLY_NUMBERS
        assert await tool.name() == "multiply"
        assert (
            await tool.description()
            == "Multiply two numbers together and return the result"
        )

    async def test_toolcall_definition(self):
        """Test MultiplyTool toolcall definition structure."""
        tool = MultiplyTool()
        definition = await tool.toolcall_definition()

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
    async def test_run_various_inputs(self, a, b, expected):
        """Test MultiplyTool run method with various inputs."""
        tool = MultiplyTool()
        result = await tool.run(a=a, b=b)
        assert result.output == expected


class TestDivideTool:
    """Test the DivideTool class."""

    async def test_init(self):
        """Test DivideTool initialization."""
        tool = DivideTool()
        assert await tool.id() == KilnBuiltInToolId.DIVIDE_NUMBERS
        assert await tool.name() == "divide"
        assert (
            await tool.description()
            == "Divide the first number by the second number and return the result"
        )

    async def test_toolcall_definition(self):
        """Test DivideTool toolcall definition structure."""
        tool = DivideTool()
        definition = await tool.toolcall_definition()

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
    async def test_run_various_inputs(self, a, b, expected):
        """Test DivideTool run method with various inputs."""
        tool = DivideTool()
        result = await tool.run(a=a, b=b)
        assert result.output == expected

    async def test_divide_by_zero(self):
        """Test that division by zero raises ZeroDivisionError."""
        tool = DivideTool()
        with pytest.raises(ZeroDivisionError, match="Cannot divide by zero"):
            await tool.run(a=5, b=0)

    async def test_divide_zero_by_zero(self):
        """Test that zero divided by zero raises ZeroDivisionError."""
        tool = DivideTool()
        with pytest.raises(ZeroDivisionError, match="Cannot divide by zero"):
            await tool.run(a=0, b=0)


class TestCalculateTool:
    """Test the CalculateTool safe expression evaluator."""

    async def test_init(self):
        tool = CalculateTool()
        assert await tool.id() == KilnBuiltInToolId.CALCULATE
        assert await tool.name() == "calculate"

    async def test_sqrt_expression(self):
        tool = CalculateTool()
        out = json.loads(
            (await tool.run(expression="sqrt(0.864 * 0.136 / 147)")).output
        )
        assert out["result"] == pytest.approx(0.0283, abs=5e-4)

    async def test_constants(self):
        tool = CalculateTool()
        out = json.loads((await tool.run(expression="2 * pi")).output)
        assert out["result"] == pytest.approx(6.283185, abs=1e-5)

    async def test_operator_precedence(self):
        tool = CalculateTool()
        out = json.loads((await tool.run(expression="2 + 3 * 4 ** 2")).output)
        assert out["result"] == 50

    async def test_disallowed_name_errors(self):
        result = await CalculateTool().run(expression="__import__('os')")
        assert result.is_error is True

    async def test_attribute_access_errors(self):
        result = await CalculateTool().run(expression="(1).__class__")
        assert result.is_error is True

    async def test_division_by_zero_errors(self):
        result = await CalculateTool().run(expression="1/0")
        assert result.is_error is True

    async def test_syntax_error(self):
        result = await CalculateTool().run(expression="1 +")
        assert result.is_error is True

    async def test_empty_expression_errors(self):
        result = await CalculateTool().run(expression="   ")
        assert result.is_error is True

    async def test_huge_exponent_guarded(self):
        result = await CalculateTool().run(expression="9 ** 99999")
        assert result.is_error is True

    async def test_huge_negative_exponent_guarded(self):
        result = await CalculateTool().run(expression="9 ** -99999")
        assert result.is_error is True

    async def test_pow_call_exponent_guarded(self):
        # The pow() function path is guarded the same as the ** operator.
        result = await CalculateTool().run(expression="pow(9, 99999)")
        assert result.is_error is True

    async def test_bad_call_arity_is_structured_error(self):
        # Wrong arity must return a structured error, not raise an uncaught TypeError.
        for expr in ("min()", "round(1, 2, 3)"):
            result = await CalculateTool().run(expression=expr)
            assert result.is_error is True, expr

    async def test_factorial_non_integer_is_structured_error(self):
        result = await CalculateTool().run(expression="factorial(1.5)")
        assert result.is_error is True

    async def test_math_domain_error_is_structured(self):
        # sqrt(-1) raises ValueError underneath; the tool surfaces it as is_error.
        result = await CalculateTool().run(expression="sqrt(-1)")
        assert result.is_error is True
