import pytest

from kiln_ai.datamodel.spec_properties import validate_string_properties


def test_validate_string_properties_all_required_fields_valid():
    """Test validation passes when all required fields are non-empty strings."""
    properties = {
        "field1": "valid value",
        "field2": "another valid value",
        "field3": "  value with spaces  ",
    }
    result = validate_string_properties(
        properties,
        required_fields=["field1", "field2", "field3"],
    )
    assert result == properties


def test_validate_string_properties_required_field_none():
    """Test validation fails when required field is None."""
    properties = {
        "field1": "valid value",
        "field2": None,
    }
    with pytest.raises(ValueError, match="field2 cannot be empty"):
        validate_string_properties(
            properties,
            required_fields=["field1", "field2"],
        )


def test_validate_string_properties_required_field_empty_string():
    """Test validation fails when required field is empty string."""
    properties = {
        "field1": "valid value",
        "field2": "",
    }
    with pytest.raises(ValueError, match="field2 cannot be empty"):
        validate_string_properties(
            properties,
            required_fields=["field1", "field2"],
        )


def test_validate_string_properties_required_field_whitespace_only():
    """Test validation fails when required field is only whitespace."""
    properties = {
        "field1": "valid value",
        "field2": "   ",
    }
    with pytest.raises(ValueError, match="field2 cannot be empty"):
        validate_string_properties(
            properties,
            required_fields=["field1", "field2"],
        )


def test_validate_string_properties_required_field_missing():
    """Test validation fails when required field is missing from dict."""
    properties = {
        "field1": "valid value",
    }
    with pytest.raises(ValueError, match="field2 cannot be empty"):
        validate_string_properties(
            properties,
            required_fields=["field1", "field2"],
        )


def test_validate_string_properties_optional_field_none():
    """Test validation passes when optional field is None."""
    properties = {
        "field1": "valid value",
        "optional_field": None,
    }
    result = validate_string_properties(
        properties,
        required_fields=["field1"],
        optional_fields=["optional_field"],
    )
    assert result == properties


def test_validate_string_properties_optional_field_valid():
    """Test validation passes when optional field has valid string."""
    properties = {
        "field1": "valid value",
        "optional_field": "optional value",
    }
    result = validate_string_properties(
        properties,
        required_fields=["field1"],
        optional_fields=["optional_field"],
    )
    assert result == properties


def test_validate_string_properties_optional_field_empty_string():
    """Test validation fails when optional field is empty string (not None)."""
    properties = {
        "field1": "valid value",
        "optional_field": "",
    }
    with pytest.raises(ValueError, match="optional_field if provided cannot be empty"):
        validate_string_properties(
            properties,
            required_fields=["field1"],
            optional_fields=["optional_field"],
        )


def test_validate_string_properties_optional_field_whitespace_only():
    """Test validation fails when optional field is only whitespace."""
    properties = {
        "field1": "valid value",
        "optional_field": "   ",
    }
    with pytest.raises(ValueError, match="optional_field if provided cannot be empty"):
        validate_string_properties(
            properties,
            required_fields=["field1"],
            optional_fields=["optional_field"],
        )


def test_validate_string_properties_optional_field_missing():
    """Test validation passes when optional field is missing from dict."""
    properties = {
        "field1": "valid value",
    }
    result = validate_string_properties(
        properties,
        required_fields=["field1"],
        optional_fields=["optional_field"],
    )
    assert result == properties


def test_validate_string_properties_no_optional_fields():
    """Test validation works when no optional fields specified."""
    properties = {
        "field1": "valid value",
        "field2": "another value",
    }
    result = validate_string_properties(
        properties,
        required_fields=["field1", "field2"],
        optional_fields=None,
    )
    assert result == properties


def test_validate_string_properties_empty_required_fields():
    """Test validation works when no required fields specified."""
    properties = {
        "optional_field": "value",
    }
    result = validate_string_properties(
        properties,
        required_fields=[],
        optional_fields=["optional_field"],
    )
    assert result == properties
