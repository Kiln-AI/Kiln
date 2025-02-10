import pytest

from kiln_ai.adapters.ml_model_list import ModelParserID
from kiln_ai.adapters.parsers.base_parser import BaseParser
from kiln_ai.adapters.parsers.parser_registry import model_parser_from_id
from kiln_ai.adapters.parsers.r1_parser import R1ThinkingParser


def test_model_parser_from_id_invalid():
    """Test that invalid parser ID raises ValueError."""

    # Create a mock enum value that isn't handled
    class MockModelParserID:
        mock_value = "mock_value"

    with pytest.raises(ValueError) as exc_info:
        model_parser_from_id(MockModelParserID.mock_value)  # type: ignore

    assert "Unhandled enum value" in str(exc_info.value)


@pytest.mark.parametrize(
    "parser_id,expected_class",
    [
        (None, BaseParser),
        (ModelParserID.r1_thinking, R1ThinkingParser),
    ],
)
def test_model_parser_from_id_parametrized(parser_id, expected_class):
    """Test all valid parser IDs using parametrize."""
    parser_class = model_parser_from_id(parser_id)
    assert parser_class == expected_class
