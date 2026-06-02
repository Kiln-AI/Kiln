import ast
import json
import math
import operator
from typing import TypedDict, Union

from kiln_ai.datamodel.tool_id import KilnBuiltInToolId
from kiln_ai.tools.base_tool import KilnTool, ToolCallResult


class AddParams(TypedDict):
    a: Union[int, float]
    b: Union[int, float]


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

    async def run(self, context=None, **kwargs) -> ToolCallResult:
        """Add two numbers and return the result."""
        kwargs = AddParams(**kwargs)  # type: ignore[missing-typed-dict-key]
        a = kwargs["a"]
        b = kwargs["b"]
        return ToolCallResult(output=str(a + b))


class SubtractParams(TypedDict):
    a: Union[int, float]
    b: Union[int, float]


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

    async def run(self, context=None, **kwargs) -> ToolCallResult:
        """Subtract b from a and return the result."""
        kwargs = SubtractParams(**kwargs)  # type: ignore[missing-typed-dict-key]
        a = kwargs["a"]
        b = kwargs["b"]
        return ToolCallResult(output=str(a - b))


class MultiplyParams(TypedDict):
    a: Union[int, float]
    b: Union[int, float]


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

    async def run(self, context=None, **kwargs) -> ToolCallResult:
        """Multiply two numbers and return the result."""
        kwargs = MultiplyParams(**kwargs)  # type: ignore[missing-typed-dict-key]
        a = kwargs["a"]
        b = kwargs["b"]
        return ToolCallResult(output=str(a * b))


class DivideParams(TypedDict):
    a: Union[int, float]
    b: Union[int, float]


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

    async def run(self, context=None, **kwargs) -> ToolCallResult:
        """Divide a by b and return the result."""
        kwargs = DivideParams(**kwargs)  # type: ignore[missing-typed-dict-key]
        a = kwargs["a"]
        b = kwargs["b"]
        if b == 0:
            raise ZeroDivisionError("Cannot divide by zero")
        return ToolCallResult(output=str(a / b))


# ---------------------------------------------------------------------------
# calculate — safe arithmetic expression evaluator (AST-sandboxed, never eval)
# ---------------------------------------------------------------------------

_CALCULATE_DESCRIPTION = """Evaluate an arithmetic expression and return the exact numeric result. Use this for any non-trivial arithmetic instead of computing it in your head (which is error-prone). Supports + - * / // % ** parentheses and the functions sqrt, log, log10, log2, exp, abs, min, max, round, floor, ceil, factorial, pow, and the constants pi, e, tau. Example: "sqrt(0.5 * 0.5 / 100)". It is NOT a general programming sandbox — only arithmetic is allowed."""

_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCS = {
    "sqrt": math.sqrt,
    "log": math.log,
    "log10": math.log10,
    "log2": math.log2,
    "exp": math.exp,
    "abs": abs,
    "min": min,
    "max": max,
    "round": round,
    "floor": math.floor,
    "ceil": math.ceil,
    "factorial": math.factorial,
    "pow": pow,
}
_NAMES = {"pi": math.pi, "e": math.e, "tau": math.tau}

# Guardrails against pathological inputs (e.g. 9**9**9) that would hang.
_MAX_POW_EXPONENT = 1000
_MAX_FACTORIAL = 1000


def _eval_node(node):
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise ValueError("Only numeric literals are allowed.")
        return node.value
    if isinstance(node, ast.BinOp):
        op = _BIN_OPS.get(type(node.op))
        if op is None:
            raise ValueError(f"Operator {type(node.op).__name__} is not allowed.")
        left, right = _eval_node(node.left), _eval_node(node.right)
        if (
            op is operator.pow
            and isinstance(right, (int, float))
            and abs(right) > _MAX_POW_EXPONENT
        ):
            raise ValueError(f"Exponent too large (max {_MAX_POW_EXPONENT}).")
        return op(left, right)
    if isinstance(node, ast.UnaryOp):
        op = _UNARY_OPS.get(type(node.op))
        if op is None:
            raise ValueError(f"Unary operator {type(node.op).__name__} is not allowed.")
        return op(_eval_node(node.operand))
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _FUNCS:
            name = getattr(node.func, "id", type(node.func).__name__)
            raise ValueError(f"Function '{name}' is not allowed.")
        if node.keywords:
            raise ValueError("Keyword arguments are not allowed.")
        fn = _FUNCS[node.func.id]
        args = [_eval_node(a) for a in node.args]
        if (
            fn is pow
            and len(args) >= 2
            and isinstance(args[1], (int, float))
            and abs(args[1]) > _MAX_POW_EXPONENT
        ):
            raise ValueError(f"Exponent too large (max {_MAX_POW_EXPONENT}).")
        if fn is math.factorial and args and args[0] > _MAX_FACTORIAL:
            raise ValueError(f"factorial argument too large (max {_MAX_FACTORIAL}).")
        # Surface bad calls (wrong arity, non-numeric args, math domain errors) as
        # structured ValueErrors so the tool returns a clean error rather than an
        # uncaught TypeError/ValueError from the underlying function.
        try:
            return fn(*args)
        except (TypeError, ValueError) as e:
            raise ValueError(str(e)) from e
    if isinstance(node, ast.Name):
        if node.id not in _NAMES:
            raise ValueError(f"Name '{node.id}' is not allowed.")
        return _NAMES[node.id]
    raise ValueError(f"Expression element {type(node).__name__} is not allowed.")


def safe_eval(expression: str) -> float:
    """Evaluate an arithmetic expression with a whitelisted AST. Raises ValueError on
    anything outside the arithmetic grammar; never uses Python ``eval``."""
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as e:
        raise ValueError(f"Could not parse expression: {e.msg}.")
    return _eval_node(tree)


class CalculateTool(KilnTool):
    """A safe arithmetic expression evaluator (AST-sandboxed, never uses eval)."""

    def __init__(self):
        super().__init__(
            tool_id=KilnBuiltInToolId.CALCULATE,
            name="calculate",
            description=_CALCULATE_DESCRIPTION,
            parameters_schema={
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "The arithmetic expression to evaluate, e.g. 'sqrt(0.5 * 0.5 / 150)'.",
                    },
                },
                "required": ["expression"],
            },
        )

    async def run(self, context=None, **kwargs) -> ToolCallResult:
        _ = context
        expression = kwargs.get("expression", "")
        if not isinstance(expression, str) or not expression.strip():
            return _calc_error(
                "'expression' is required and must be a non-empty string."
            )
        try:
            result = safe_eval(expression)
        except ValueError as e:
            return _calc_error(str(e))
        except ZeroDivisionError:
            return _calc_error("Division by zero.")
        except (OverflowError, ArithmeticError) as e:
            return _calc_error(f"Arithmetic error: {e}")

        out = {"operation": "calculate", "expression": expression, "result": result}
        return ToolCallResult(output=json.dumps(out, ensure_ascii=False))


def _calc_error(msg: str) -> ToolCallResult:
    return ToolCallResult(
        output=json.dumps({"error": msg}, ensure_ascii=False),
        is_error=True,
        error_message=msg,
    )
