import pytest
from pydantic import ValidationError

from kiln_ai.datamodel.external_tool import ExternalToolServer, ToolServerType


def test_external_tool_creation():
    """Test successful creation of ExternalToolServer with valid data."""
    tool = ExternalToolServer(
        name="test_tool",
        type=ToolServerType.remote_mcp,
        description="A test external tool",
        properties={
            "server_url": "https://api.example.com",
            "headers": {
                "Authorization": "Bearer token123",
                "Content-Type": "application/json",
            },
        },
    )

    assert tool.name == "test_tool"
    assert tool.description == "A test external tool"
    assert tool.properties["server_url"] == "https://api.example.com"
    assert tool.properties["headers"] == {
        "Authorization": "Bearer token123",
        "Content-Type": "application/json",
    }
    assert tool.id is not None  # Should have auto-generated ID


def test_external_tool_server_creation_minimal():
    """Test creation of ExternalToolServer with minimal required fields."""
    tool = ExternalToolServer(
        name="minimal_tool",
        type=ToolServerType.remote_mcp,
        properties={
            "server_url": "https://api.example.com",
            "headers": {"Authorization": "Bearer token"},
        },
    )

    assert tool.name == "minimal_tool"
    assert tool.description is None
    assert tool.properties["server_url"] == "https://api.example.com"
    assert tool.properties["headers"] == {"Authorization": "Bearer token"}


def test_external_tool_server_name_validation():
    """Test that name field validates as FilenameString."""
    # Test valid names
    valid_names = ["test_tool", "Tool123", "my-tool", "Tool_Name_v2"]
    for name in valid_names:
        tool = ExternalToolServer(
            name=name,
            type=ToolServerType.remote_mcp,
            properties={
                "server_url": "https://api.example.com",
                "headers": {"Authorization": "Bearer token"},
            },
        )
        assert tool.name == name

    # Test invalid names (forbidden characters in filenames)
    invalid_names = [
        "tool/with/slash",
        "tool\\with\\backslash",
        "tool?with?question",
        "tool*with*asterisk",
        "tool:with:colon",
        "tool|with|pipe",
        'tool"with"quote',
        "tool<with>brackets",
        "tool,with,comma",
        "tool;with;semicolon",
        "tool=with=equals",
        "tool\nwith\nnewline",
    ]

    for invalid_name in invalid_names:
        with pytest.raises(ValidationError):
            ExternalToolServer(
                name=invalid_name,
                type=ToolServerType.remote_mcp,
                properties={
                    "server_url": "https://api.example.com",
                    "headers": {"Authorization": "Bearer token"},
                },
            )


def test_external_tool_name_length_constraints():
    """Test name length constraints (FilenameString: 1-120 chars)."""
    # Test empty name
    with pytest.raises(ValidationError):
        ExternalToolServer(
            name="",
            type=ToolServerType.remote_mcp,
            properties={
                "server_url": "https://api.example.com",
                "headers": {"Authorization": "Bearer token"},
            },
        )

    # Test name that's too long (> 120 chars)
    long_name = "a" * 121
    with pytest.raises(ValidationError):
        ExternalToolServer(
            name=long_name,
            type=ToolServerType.remote_mcp,
            properties={
                "server_url": "https://api.example.com",
                "headers": {"Authorization": "Bearer token"},
            },
        )

    # Test maximum valid length (120 chars)
    max_name = "a" * 120
    tool = ExternalToolServer(
        name=max_name,
        type=ToolServerType.remote_mcp,
        properties={
            "server_url": "https://api.example.com",
            "headers": {"Authorization": "Bearer token"},
        },
    )
    assert tool.name == max_name


def test_external_tool_required_fields():
    """Test that missing required fields raise ValidationError."""
    # Missing name
    with pytest.raises(ValidationError):
        ExternalToolServer(
            type=ToolServerType.remote_mcp,
            properties={
                "server_url": "https://api.example.com",
                "headers": {"Authorization": "Bearer token"},
            },
        )  # type: ignore

    # Missing server_url
    with pytest.raises(ValidationError):
        ExternalToolServer(
            name="test_tool",
            type=ToolServerType.remote_mcp,
            properties={
                "headers": {"Authorization": "Bearer token"},
            },
        )

    # Missing type
    with pytest.raises(ValidationError):
        ExternalToolServer(
            name="test_tool",
            properties={
                "server_url": "https://api.example.com",
                "headers": {"Authorization": "Bearer token"},
            },
        )  # type: ignore

    # Missing headers
    with pytest.raises(ValidationError):
        ExternalToolServer(
            name="test_tool",
            type=ToolServerType.remote_mcp,
            properties={
                "server_url": "https://api.example.com",
            },
        )


def test_external_tool_empty_string_validation():
    """Test that empty strings for required fields raise ValidationError."""
    # Empty server_url
    with pytest.raises(ValidationError):
        ExternalToolServer(
            name="test_tool",
            type=ToolServerType.remote_mcp,
            properties={
                "server_url": "",
                "headers": {"Authorization": "Bearer token"},
            },
        )


def test_external_tool_headers_validation():
    """Test headers field validation."""
    # Valid headers (including empty headers)
    valid_headers = [
        {},  # Empty headers are now allowed
        {"Authorization": "Bearer token123"},
        {"Content-Type": "application/json", "Accept": "application/json"},
        {"X-API-Key": "secret", "User-Agent": "MyApp/1.0"},
        {"Custom-Header": "value", "Another-Header": "another-value"},
    ]

    for headers in valid_headers:
        tool = ExternalToolServer(
            name="test_tool",
            type=ToolServerType.remote_mcp,
            properties={
                "server_url": "https://api.example.com",
                "headers": headers,
            },
        )
        assert tool.properties["headers"] == headers

    # Test that None headers are rejected for remote_mcp type
    with pytest.raises(
        ValidationError, match="headers must be set when type is 'remote_mcp'"
    ):
        ExternalToolServer(
            name="test_tool",
            type=ToolServerType.remote_mcp,
            properties={
                "server_url": "https://api.example.com",
                "headers": None,
            },
        )

    # Test that empty headers dict is allowed
    tool = ExternalToolServer(
        name="test_tool",
        type=ToolServerType.remote_mcp,
        properties={
            "server_url": "https://api.example.com",
            "headers": {},
        },
    )
    assert tool.properties["headers"] == {}


def test_external_tool_server_url_validation():
    """Test server_url field validation."""
    # Valid URLs
    valid_urls = [
        "https://api.example.com",
        "http://localhost:8080",
        "https://api.service.com/v1/mcp",
        "wss://websocket.example.com",
        "http://192.168.1.1:3000/api",
    ]

    for url in valid_urls:
        tool = ExternalToolServer(
            name="test_tool",
            type=ToolServerType.remote_mcp,
            properties={
                "server_url": url,
                "headers": {"Authorization": "Bearer token"},
            },
        )
        assert tool.properties["server_url"] == url


def test_external_tool_description_optional():
    """Test that description field is optional and can be None."""
    # With description
    tool_with_desc = ExternalToolServer(
        name="test_tool",
        type=ToolServerType.remote_mcp,
        description="A test tool",
        properties={
            "server_url": "https://api.example.com",
            "headers": {"Authorization": "Bearer token"},
        },
    )
    assert tool_with_desc.description == "A test tool"

    # Without description (should be None)
    tool_without_desc = ExternalToolServer(
        name="test_tool",
        type=ToolServerType.remote_mcp,
        properties={
            "server_url": "https://api.example.com",
            "headers": {"Authorization": "Bearer token"},
        },
    )
    assert tool_without_desc.description is None

    # Explicitly set to None
    tool_none_desc = ExternalToolServer(
        name="test_tool",
        type=ToolServerType.remote_mcp,
        description=None,
        properties={
            "server_url": "https://api.example.com",
            "headers": {"Authorization": "Bearer token"},
        },
    )
    assert tool_none_desc.description is None


def test_external_tool_inheritance():
    """Test that ExternalToolServer properly inherits from KilnParentedModel."""
    tool = ExternalToolServer(
        name="test_tool",
        type=ToolServerType.remote_mcp,
        properties={
            "server_url": "https://api.example.com",
            "headers": {"Authorization": "Bearer token"},
        },
    )

    # Should have inherited fields from KilnBaseModel
    assert hasattr(tool, "id")
    assert hasattr(tool, "created_at")
    assert hasattr(tool, "created_by")
    assert hasattr(tool, "v")
    assert hasattr(tool, "model_type")

    # Should have inherited fields from KilnParentedModel
    assert hasattr(tool, "parent")

    # Test model_type
    assert tool.model_type == "external_tool_server"


def test_external_tool_model_validation_assignment():
    """Test that model validation works on assignment."""
    tool = ExternalToolServer(
        name="test_tool",
        type=ToolServerType.remote_mcp,
        properties={
            "server_url": "https://api.example.com",
            "headers": {"Authorization": "Bearer token"},
        },
    )

    # Valid assignment should work
    tool.name = "new_name"
    assert tool.name == "new_name"

    # Valid headers assignment should work
    tool.properties["headers"] = {"X-API-Key": "new-key"}
    assert tool.properties["headers"] == {"X-API-Key": "new-key"}

    # Invalid assignment should raise ValidationError
    with pytest.raises(ValidationError):
        tool.name = "invalid/name/with/slashes"

    with pytest.raises(ValidationError):
        tool.properties["server_url"] = ""
        # Trigger validation by reassigning the properties dict
        tool.properties = tool.properties

    # Invalid headers assignment (None) should raise ValidationError
    with pytest.raises(ValidationError):
        tool.properties["headers"] = None
        # Trigger validation by reassigning the properties dict
        tool.properties = tool.properties

    # Invalid headers assignment (empty dict) should raise ValidationError
    with pytest.raises(ValidationError):
        tool.properties["headers"] = {}
        # Trigger validation by reassigning the properties dict
        tool.properties = tool.properties
