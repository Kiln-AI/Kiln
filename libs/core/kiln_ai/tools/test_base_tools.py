import pytest

from kiln_ai.tools.base_tool import KilnTool, KilnToolInterface


class TestKilnToolInterface:
    """Test the abstract KilnToolInterface."""

    def test_cannot_instantiate_abstract_class(self):
        """Test that KilnToolInterface cannot be instantiated directly."""
        with pytest.raises(TypeError):
            KilnToolInterface()  # type: ignore


class ConcreteTestTool(KilnTool):
    """Concrete implementation of KilnTool for testing."""

    def run(self, **kwargs) -> str:
        return f"test_result: {kwargs}"


class TestKilnTool:
    """Test the KilnTool base class."""

    async def test_init_with_valid_schema(self):
        """Test KilnTool initialization with valid parameters schema."""
        schema = {
            "type": "object",
            "properties": {
                "param1": {"type": "string", "description": "Test parameter"}
            },
            "required": ["param1"],
        }

        tool = ConcreteTestTool(
            tool_id="test_tool_id",
            name="test_tool",
            description="A test tool",
            parameters_schema=schema,
        )

        assert await tool.id() == "test_tool_id"
        assert await tool.name() == "test_tool"
        assert await tool.description() == "A test tool"
        assert tool._parameters_schema == schema

    async def test_init_with_invalid_schema_missing_type(self):
        """Test KilnTool initialization fails with schema missing type."""
        invalid_schema = {"properties": {"param1": {"type": "string"}}}

        with pytest.raises(
            ValueError, match="JSON schema must be an object with properties"
        ):
            ConcreteTestTool(
                tool_id="test_tool",
                name="test_tool",
                description="A test tool",
                parameters_schema=invalid_schema,
            )

    def test_init_with_invalid_schema_missing_properties(self):
        """Test KilnTool initialization fails with schema missing properties."""
        invalid_schema = {"type": "object"}

        with pytest.raises(
            ValueError, match="JSON schema must be an object with properties"
        ):
            ConcreteTestTool(
                tool_id="test_tool",
                name="test_tool",
                description="A test tool",
                parameters_schema=invalid_schema,
            )

    def test_init_with_invalid_schema_wrong_type(self):
        """Test KilnTool initialization fails with schema of wrong type."""
        invalid_schema = {"type": "array", "properties": {"param1": {"type": "string"}}}

        with pytest.raises(
            ValueError, match="JSON schema must be an object with properties"
        ):
            ConcreteTestTool(
                tool_id="test_tool",
                name="test_tool",
                description="A test tool",
                parameters_schema=invalid_schema,
            )

    async def test_toolcall_definition(self):
        """Test that toolcall_definition returns correct OpenAI-compatible format."""
        schema = {
            "type": "object",
            "properties": {
                "param1": {"type": "string", "description": "Test parameter"},
                "param2": {"type": "integer", "description": "Another parameter"},
            },
            "required": ["param1"],
        }

        tool = ConcreteTestTool(
            tool_id="test_tool_id",
            name="test_function",
            description="A test function tool",
            parameters_schema=schema,
        )

        definition = await tool.toolcall_definition()

        expected = {
            "type": "function",
            "function": {
                "name": "test_function",
                "description": "A test function tool",
                "parameters": schema,
            },
        }

        assert definition == expected

    def test_run_method_implemented_by_subclass(self):
        """Test that the run method works when implemented by subclass."""
        schema = {
            "type": "object",
            "properties": {"message": {"type": "string"}},
            "required": ["message"],
        }

        tool = ConcreteTestTool(
            tool_id="test_tool",
            name="test_tool",
            description="A test tool",
            parameters_schema=schema,
        )

        result = tool.run(message="hello", extra_param=42)
        assert result == "test_result: {'message': 'hello', 'extra_param': 42}"

    def test_cannot_instantiate_abstract_kiln_tool_directly(self):
        """Test that KilnTool cannot be instantiated directly due to abstract run method."""
        schema = {
            "type": "object",
            "properties": {"param": {"type": "string"}},
            "required": ["param"],
        }

        with pytest.raises(TypeError):
            KilnTool(
                tool_id="test",
                name="test",
                description="test",
                parameters_schema=schema,
            )  # type: ignore


class TestValidationEdgeCases:
    """Test edge cases and validation scenarios."""

    def test_empty_properties_schema(self):
        """Test schema with empty properties is valid."""
        schema = {"type": "object", "properties": {}}

        tool = ConcreteTestTool(
            tool_id="test_tool",
            name="test_tool",
            description="A test tool",
            parameters_schema=schema,
        )

        assert tool._parameters_schema == schema

    async def test_complex_nested_schema(self):
        """Test complex nested schema validation."""
        schema = {
            "type": "object",
            "properties": {
                "config": {
                    "type": "object",
                    "properties": {
                        "timeout": {"type": "integer", "minimum": 0},
                        "retries": {"type": "integer", "minimum": 1},
                    },
                    "required": ["timeout"],
                },
                "items": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["config"],
        }

        tool = ConcreteTestTool(
            tool_id="complex_tool",
            name="complex_tool",
            description="A complex test tool",
            parameters_schema=schema,
        )

        assert tool._parameters_schema == schema

        definition = await tool.toolcall_definition()
        assert definition["function"]["parameters"] == schema
