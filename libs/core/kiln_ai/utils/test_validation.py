import pytest

from kiln_ai.utils.validation import (
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
