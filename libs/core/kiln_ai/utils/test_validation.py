from typing import TypedDict

import pytest
from pydantic import BaseModel

from kiln_ai.utils.validation import (
    NonEmptyString,
    string_not_empty,
    tool_name_validator,
    validate_return_dict_prop,
    validate_return_dict_prop_optional,
)


class TestValidateReturnDictProp:
    """Test cases for validate_return_dict_prop function."""

    def test_valid_string_property(self):
        """Test validation succeeds for valid string property."""
        test_dict = {"name": "test_value"}
        result = validate_return_dict_prop(test_dict, "name", str, "prefix")
        assert result == "test_value"

    def test_valid_int_property(self):
        """Test validation succeeds for valid integer property."""
        test_dict = {"count": 42}
        result = validate_return_dict_prop(test_dict, "count", int, "prefix")
        assert result == 42

    def test_valid_bool_property(self):
        """Test validation succeeds for valid boolean property."""
        test_dict = {"enabled": True}
        result = validate_return_dict_prop(test_dict, "enabled", bool, "prefix")
        assert result is True

    def test_valid_list_property(self):
        """Test validation succeeds for valid list property."""
        test_dict = {"items": [1, 2, 3]}
        result = validate_return_dict_prop(test_dict, "items", list, "prefix")
        assert result == [1, 2, 3]

    def test_valid_dict_property(self):
        """Test validation succeeds for valid dict property."""
        test_dict = {"config": {"key": "value"}}
        result = validate_return_dict_prop(test_dict, "config", dict, "prefix")
        assert result == {"key": "value"}

    def test_missing_key_raises_error(self):
        """Test that missing key raises ValueError with appropriate message."""
        test_dict = {"other_key": "value"}
        with pytest.raises(ValueError) as exc_info:
            validate_return_dict_prop(test_dict, "missing_key", str, "prefix")

        expected_msg = "prefix missing_key is a required property"
        assert str(exc_info.value) == expected_msg

    def test_wrong_type_raises_error(self):
        """Test that wrong type raises ValueError with appropriate message."""
        test_dict = {"count": "not_a_number"}
        with pytest.raises(ValueError) as exc_info:
            validate_return_dict_prop(test_dict, "count", int, "prefix")

        expected_msg = "prefix count must be of type <class 'int'>"
        assert str(exc_info.value) == expected_msg

    def test_none_value_with_none_type(self):
        """Test that None value validates correctly when expecting NoneType."""
        test_dict = {"value": None}
        result = validate_return_dict_prop(test_dict, "value", type(None), "prefix")
        assert result is None

    def test_none_value_with_string_type_raises_error(self):
        """Test that None value raises error when expecting string."""
        test_dict = {"value": None}
        with pytest.raises(ValueError) as exc_info:
            validate_return_dict_prop(test_dict, "value", str, "prefix")

        expected_msg = "prefix value must be of type <class 'str'>"
        assert str(exc_info.value) == expected_msg

    @pytest.mark.parametrize(
        "test_value,expected_type",
        [
            ("string", str),
            (123, int),
            (3.14, float),
            (True, bool),
            ([1, 2, 3], list),
            ({"k": "v"}, dict),
            ((1, 2), tuple),
            ({1, 2, 3}, set),
        ],
    )
    def test_various_types_succeed(self, test_value, expected_type):
        """Test validation succeeds for various types."""
        test_dict = {"value": test_value}
        result = validate_return_dict_prop(test_dict, "value", expected_type, "prefix")
        assert result == test_value
        assert isinstance(result, expected_type)

    @pytest.mark.parametrize(
        "test_value,wrong_type",
        [
            ("string", int),
            (123, str),
            (3.14, int),
            (True, str),
            ([1, 2, 3], dict),
            ({"k": "v"}, list),
            ((1, 2), list),
            ({1, 2, 3}, list),
        ],
    )
    def test_various_types_fail(self, test_value, wrong_type):
        """Test validation fails for wrong types."""
        test_dict = {"value": test_value}
        with pytest.raises(ValueError):
            validate_return_dict_prop(test_dict, "value", wrong_type, "prefix")

    def test_empty_dict_raises_error(self):
        """Test that empty dictionary raises error for any key."""
        test_dict = {}
        with pytest.raises(ValueError) as exc_info:
            validate_return_dict_prop(test_dict, "any_key", str, "prefix")

        expected_msg = "prefix any_key is a required property"
        assert str(exc_info.value) == expected_msg

    def test_empty_string_key(self):
        """Test validation with empty string as key."""
        test_dict = {"": "empty_key_value"}
        result = validate_return_dict_prop(test_dict, "", str, "prefix")
        assert result == "empty_key_value"

    def test_numeric_values_and_inheritance(self):
        """Test that isinstance works correctly with numeric inheritance."""
        # bool is a subclass of int in Python, so True/False are valid ints
        test_dict = {"flag": True}
        result = validate_return_dict_prop(test_dict, "flag", int, "prefix")
        assert result is True
        assert isinstance(result, int)  # This should pass since bool inherits from int


class TestValidateReturnDictPropOptional:
    """Test cases for validate_return_dict_prop_optional function."""

    def test_valid_string_property(self):
        """Test validation succeeds for valid string property."""
        test_dict = {"name": "test_value"}
        result = validate_return_dict_prop_optional(test_dict, "name", str, "prefix")
        assert result == "test_value"

    def test_valid_int_property(self):
        """Test validation succeeds for valid integer property."""
        test_dict = {"count": 42}
        result = validate_return_dict_prop_optional(test_dict, "count", int, "prefix")
        assert result == 42

    def test_missing_key_returns_none(self):
        """Test that missing key returns None instead of raising error."""
        test_dict = {"other_key": "value"}
        result = validate_return_dict_prop_optional(
            test_dict, "missing_key", str, "prefix"
        )
        assert result is None

    def test_none_value_returns_none(self):
        """Test that None value returns None."""
        test_dict = {"value": None}
        result = validate_return_dict_prop_optional(test_dict, "value", str, "prefix")
        assert result is None

    def test_empty_dict_returns_none(self):
        """Test that empty dictionary returns None for any key."""
        test_dict = {}
        result = validate_return_dict_prop_optional(test_dict, "any_key", str, "prefix")
        assert result is None

    def test_wrong_type_raises_error(self):
        """Test that wrong type still raises ValueError (delegates to required function)."""
        test_dict = {"count": "not_a_number"}
        with pytest.raises(ValueError) as exc_info:
            validate_return_dict_prop_optional(test_dict, "count", int, "prefix")

        expected_msg = "prefix count must be of type <class 'int'>"
        assert str(exc_info.value) == expected_msg

    def test_explicit_none_vs_missing_key(self):
        """Test that explicit None value and missing key both return None."""
        # Missing key
        test_dict_missing = {"other": "value"}
        result_missing = validate_return_dict_prop_optional(
            test_dict_missing, "target", str, "prefix"
        )
        assert result_missing is None

        # Explicit None
        test_dict_none = {"target": None}
        result_none = validate_return_dict_prop_optional(
            test_dict_none, "target", str, "prefix"
        )
        assert result_none is None

    @pytest.mark.parametrize(
        "test_value,expected_type",
        [
            ("string", str),
            (123, int),
            (3.14, float),
            (True, bool),
            ([1, 2, 3], list),
            ({"k": "v"}, dict),
            ((1, 2), tuple),
            ({1, 2, 3}, set),
        ],
    )
    def test_various_types_succeed(self, test_value, expected_type):
        """Test validation succeeds for various types."""
        test_dict = {"value": test_value}
        result = validate_return_dict_prop_optional(
            test_dict, "value", expected_type, "prefix"
        )
        assert result == test_value
        assert isinstance(result, expected_type)

    @pytest.mark.parametrize(
        "test_value,wrong_type",
        [
            ("string", int),
            (123, str),
            (3.14, int),
            (True, str),
            ([1, 2, 3], dict),
            ({"k": "v"}, list),
            ((1, 2), list),
            ({1, 2, 3}, list),
        ],
    )
    def test_various_types_fail(self, test_value, wrong_type):
        """Test validation fails for wrong types (delegates to required function)."""
        test_dict = {"value": test_value}
        with pytest.raises(ValueError):
            validate_return_dict_prop_optional(test_dict, "value", wrong_type, "prefix")

    def test_empty_string_key_with_value(self):
        """Test validation with empty string as key when value exists."""
        test_dict = {"": "empty_key_value"}
        result = validate_return_dict_prop_optional(test_dict, "", str, "prefix")
        assert result == "empty_key_value"

    def test_empty_string_key_missing(self):
        """Test validation with empty string as key when key is missing."""
        test_dict = {"other": "value"}
        result = validate_return_dict_prop_optional(test_dict, "", str, "prefix")
        assert result is None

    def test_numeric_inheritance_behavior(self):
        """Test that isinstance works correctly with numeric inheritance."""
        # bool is a subclass of int in Python, so True/False are valid ints
        test_dict = {"flag": True}
        result = validate_return_dict_prop_optional(test_dict, "flag", int, "prefix")
        assert result is True
        assert isinstance(result, int)

    def test_optional_with_zero_values(self):
        """Test that zero-like values (0, False, [], {}) are not treated as None."""
        test_cases = [
            ({"count": 0}, "count", int, 0),
            ({"flag": False}, "flag", bool, False),
            ({"items": []}, "items", list, []),
            ({"config": {}}, "config", dict, {}),
            ({"text": ""}, "text", str, ""),
        ]

        for test_dict, key, expected_type, expected_value in test_cases:
            result = validate_return_dict_prop_optional(
                test_dict, key, expected_type, "prefix"
            )
            assert result == expected_value
            assert result is not None


class TestToolNameValidator:
    """Test cases for tool_name_validator function."""

    def test_valid_simple_name(self):
        """Test validation succeeds for simple valid tool names."""
        valid_names = [
            "tool",
            "my_tool",
            "data_processor",
            "test123",
            "a",
            "tool_v2",
            "get_weather",
        ]
        for name in valid_names:
            result = tool_name_validator(name)
            assert result == name

    def test_valid_name_with_numbers(self):
        """Test validation succeeds for tool names with numbers."""
        valid_names = [
            "tool1",
            "my_tool_v2",
            "data_processor_3000",
            "test_123_abc",
            "version2",
        ]
        for name in valid_names:
            result = tool_name_validator(name)
            assert result == name

    def test_none_name_raises_error(self):
        """Test that None name raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            tool_name_validator(None)
        assert str(exc_info.value) == "Tool name cannot be empty"

    def test_empty_string_raises_error(self):
        """Test that empty string raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            tool_name_validator("")
        assert str(exc_info.value) == "Tool name cannot be empty"

    def test_whitespace_only_raises_error(self):
        """Test that whitespace-only string raises ValueError."""
        whitespace_names = [" ", "  ", "\t", "\n", "   \t  "]
        for name in whitespace_names:
            with pytest.raises(ValueError) as exc_info:
                tool_name_validator(name)
            assert str(exc_info.value) == "Tool name cannot be empty"

    def test_non_string_raises_error(self):
        """Test that non-string input raises ValueError."""
        non_string_inputs = [123, [], {}, True, 3.14]
        for input_val in non_string_inputs:
            with pytest.raises(ValueError) as exc_info:
                tool_name_validator(input_val)
            assert str(exc_info.value) == "Tool name must be a string"

    def test_uppercase_letters_raise_error(self):
        """Test that uppercase letters raise ValueError."""
        invalid_names = [
            "Tool",
            "MY_TOOL",
            "myTool",
            "tool_Name",
            "TOOL",
            "Test123",
        ]
        for name in invalid_names:
            with pytest.raises(ValueError) as exc_info:
                tool_name_validator(name)
            assert "Tool name must be in snake_case" in str(exc_info.value)

    def test_special_characters_raise_error(self):
        """Test that special characters raise ValueError."""
        invalid_names = [
            "tool-name",
            "tool.name",
            "tool@name",
            "tool#name",
            "tool$name",
            "tool%name",
            "tool&name",
            "tool*name",
            "tool+name",
            "tool=name",
            "tool!name",
            "tool?name",
            "tool name",  # space
            "tool,name",
            "tool;name",
            "tool:name",
            "tool'name",
            'tool"name',
            "tool(name)",
            "tool[name]",
            "tool{name}",
            "tool/name",
            "tool\\name",
        ]
        for name in invalid_names:
            with pytest.raises(ValueError) as exc_info:
                tool_name_validator(name)
            assert "Tool name must be in snake_case" in str(exc_info.value)

    def test_starts_with_underscore_raises_error(self):
        """Test that names starting with underscore raise ValueError."""
        invalid_names = ["_tool", "_my_tool", "_", "_123"]
        for name in invalid_names:
            with pytest.raises(ValueError) as exc_info:
                tool_name_validator(name)
            assert (
                str(exc_info.value)
                == "Tool name cannot start or end with an underscore"
            )

    def test_ends_with_underscore_raises_error(self):
        """Test that names ending with underscore raise ValueError."""
        invalid_names = ["tool_", "my_tool_", "test_"]
        for name in invalid_names:
            with pytest.raises(ValueError) as exc_info:
                tool_name_validator(name)
            assert (
                str(exc_info.value)
                == "Tool name cannot start or end with an underscore"
            )

    def test_consecutive_underscores_raise_error(self):
        """Test that consecutive underscores raise ValueError."""
        invalid_names = [
            "tool__name",
            "my__tool",
            "test___name",
            "a__b__c",
            "tool____name",
        ]
        for name in invalid_names:
            with pytest.raises(ValueError) as exc_info:
                tool_name_validator(name)
            assert (
                str(exc_info.value)
                == "Tool name cannot contain consecutive underscores"
            )

    def test_starts_with_number_raises_error(self):
        """Test that names starting with number raise ValueError."""
        invalid_names = ["1tool", "2_tool", "123abc", "9test"]
        for name in invalid_names:
            with pytest.raises(ValueError) as exc_info:
                tool_name_validator(name)
            assert str(exc_info.value) == "Tool name must start with a lowercase letter"

    def test_starts_with_underscore_number_raises_error(self):
        """Test that names starting with underscore followed by number raise ValueError."""
        invalid_names = ["_1tool", "_2tool"]
        for name in invalid_names:
            with pytest.raises(ValueError) as exc_info:
                tool_name_validator(name)
            # This should fail on the underscore check first
            assert (
                str(exc_info.value)
                == "Tool name cannot start or end with an underscore"
            )

    def test_long_name_raises_error(self):
        """Test that names longer than 64 characters raise ValueError."""
        # Create a 65-character name
        long_name = "a" * 65
        with pytest.raises(ValueError) as exc_info:
            tool_name_validator(long_name)
        assert str(exc_info.value) == "Tool name must be less than 64 characters long"

    def test_exactly_64_characters_succeeds(self):
        """Test that names with exactly 64 characters succeed."""
        # Create a 64-character name
        max_length_name = "a" * 64
        result = tool_name_validator(max_length_name)
        assert result == max_length_name

    def test_boundary_length_cases(self):
        """Test various boundary cases for name length."""
        # Test lengths around the limit
        test_cases = [
            ("a", 1),  # minimum valid length
            ("ab", 2),
            ("a" * 63, 63),  # just under limit
            ("a" * 64, 64),  # exactly at limit
        ]

        for name, expected_length in test_cases:
            result = tool_name_validator(name)
            assert result == name
            assert len(result) == expected_length

    def test_complex_valid_names(self):
        """Test complex but valid tool names."""
        valid_names = [
            "get_user_data",
            "process_payment_info",
            "validate_email_address",
            "send_notification_v2",
            "calculate_tax_amount",
            "fetch_weather_data_for_city",
            "convert_currency_usd_to_eur",
            "a1b2c3d4e5f6g7h8i9j0",
            "tool_with_many_underscores_and_numbers_123",
        ]
        for name in valid_names:
            result = tool_name_validator(name)
            assert result == name

    @pytest.mark.parametrize(
        "invalid_name,expected_error",
        [
            (None, "Tool name cannot be empty"),
            ("", "Tool name cannot be empty"),
            ("   ", "Tool name cannot be empty"),
            (123, "Tool name must be a string"),
            ("Tool", "Tool name must be in snake_case"),
            ("tool-name", "Tool name must be in snake_case"),
            ("_tool", "Tool name cannot start or end with an underscore"),
            ("tool_", "Tool name cannot start or end with an underscore"),
            ("tool__name", "Tool name cannot contain consecutive underscores"),
            ("1tool", "Tool name must start with a lowercase letter"),
            ("a" * 65, "Tool name must be less than 64 characters long"),
        ],
    )
    def test_parametrized_invalid_cases(self, invalid_name, expected_error):
        """Test various invalid cases with parameterized inputs."""
        with pytest.raises(ValueError) as exc_info:
            tool_name_validator(invalid_name)
        assert expected_error in str(exc_info.value)

    def test_edge_case_single_character_names(self):
        """Test single character names (valid and invalid)."""
        # Valid single characters
        valid_chars = "abcdefghijklmnopqrstuvwxyz"
        for char in valid_chars:
            result = tool_name_validator(char)
            assert result == char

        # Invalid single characters
        invalid_chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-+="
        for char in invalid_chars:
            with pytest.raises(ValueError):
                tool_name_validator(char)


class SampleTypedDict(TypedDict, total=True):
    name: NonEmptyString


class SampleModel(BaseModel):
    name: NonEmptyString


class SampleNestedTypedDict(BaseModel):
    d: SampleTypedDict


class TestStringNotEmpty:
    """Test cases for string_not_empty function."""

    def test_valid_string(self):
        """Test validation succeeds for valid string."""
        result = string_not_empty("test")
        assert result == "test"

    def test_empty_string_raises_error(self):
        """Test that empty string raises ValueError."""
        with pytest.raises(ValueError):
            string_not_empty("")

    def test_valid_pydantic_model(self):
        with pytest.raises(ValueError):
            SampleModel(name="")

    def test_valid_nested_typed_dict(self):
        result = SampleNestedTypedDict(d={"name": "test"})
        assert result.d == {"name": "test"}

    def test_invalid_nested_typed_dict(self):
        with pytest.raises(ValueError):
            SampleNestedTypedDict(d={"name": ""})
