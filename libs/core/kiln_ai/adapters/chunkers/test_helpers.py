import pytest

from kiln_ai.adapters.chunkers.helpers import clean_up_text


def generate_consecutive_char_string(length: int, char: str) -> str:
    return char * length


@pytest.mark.parametrize(
    "text,expected",
    [
        # Test single newlines (should remain unchanged)
        ("Hello\nWorld", "Hello\nWorld"),
        ("Hello\n\nWorld", "Hello\n\nWorld"),
        ("Hello\n\n\nWorld", "Hello\n\n\nWorld"),
        ("Hello\n\n\n\nWorld", "Hello\n\n\n\nWorld"),
        ("Hello\n\n\n\n\nWorld", "Hello\n\n\n\n\nWorld"),
        # Test 6+ consecutive newlines (should be replaced with exactly 6)
        ("Hello\n\n\n\n\n\nWorld", "Hello\n\n\n\n\n\nWorld"),  # exactly 6, unchanged
        ("Hello\n\n\n\n\n\n\nWorld", "Hello\n\n\n\n\n\nWorld"),  # 7 newlines -> 6
        ("Hello\n\n\n\n\n\n\n\nWorld", "Hello\n\n\n\n\n\nWorld"),  # 8 newlines -> 6
        (
            "Hello\n\n\n\n\n\n\n\n\n\nWorld",
            "Hello\n\n\n\n\n\nWorld",
        ),  # 10 newlines -> 6
        # Test single spaces (should remain unchanged)
        ("Hello World", "Hello World"),
        ("Hello  World", "Hello  World"),
        ("Hello   World", "Hello   World"),
        ("Hello    World", "Hello    World"),
        ("Hello     World", "Hello     World"),
        # Test 50+ consecutive spaces (should be replaced with exactly 50)
        (
            "Hello" + " " * 50 + "World",
            "Hello" + " " * 50 + "World",
        ),  # exactly 50, unchanged
        ("Hello" + " " * 51 + "World", "Hello" + " " * 50 + "World"),  # 51 spaces -> 50
        (
            "Hello" + " " * 100 + "World",
            "Hello" + " " * 50 + "World",
        ),  # 100 spaces -> 50
        # Test mixed cases
        (
            "Hello\n\n\n\n\n\n\nWorld" + " " * 60 + "Test",
            "Hello\n\n\n\n\n\nWorld" + " " * 50 + "Test",
        ),
        (
            "Text\n\n\n\n\n\n\n\n\n\nMore" + " " * 30 + "Text",
            "Text\n\n\n\n\n\nMore" + " " * 30 + "Text",
        ),
    ],
)
def test_clean_up_text(text, expected):
    assert clean_up_text(text) == expected


text = """Water is an inorganic compound with the chemical formula H2O. It is a transparent, tasteless, odorless,[c] and nearly colorless chemical substance. It is the main constituent of Earth's hydrosphere and the fluids of all known living organisms in which it acts as a solvent. Water, being a polar molecule, undergoes strong intermolecular hydrogen bonding which is a large contributor to its physical and chemical properties.[20] It is vital for all known forms of life, despite not providing food energy or being an organic micronutrient. Due to its presence in all organisms, its chemical stability, its worldwide abundance and its strong polarity relative to its small molecular size; water is often referred to as the "universal solvent".[21]"""

long_whitespace_string = generate_consecutive_char_string(1000, " ")
long_newlines_string = generate_consecutive_char_string(1000, "\n")

string_with_whitespace = f"{text}{long_whitespace_string}{text}"
string_with_newlines = f"{text}{long_newlines_string}{text}"


@pytest.mark.parametrize(
    "text,expected",
    [
        (f"{text}{long_whitespace_string}{text}", f"{text}{' ' * 50}{text}"),
        (f"{text}{long_newlines_string}{text}", f"{text}{chr(10) * 6}{text}"),
    ],
)
def test_clean_up_text_large_text(text, expected):
    assert clean_up_text(text) == expected
