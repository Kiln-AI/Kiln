from kiln_ai.utils.name_generator import ADJECTIVES, NOUNS, generate_memorable_name


def test_generate_memorable_name_format():
    """Test that generated name follows the expected format."""
    name = generate_memorable_name()

    # Check that we get exactly two words
    words = name.split()
    assert len(words) == 2

    # Check that first word is an adjective and second word is a noun
    assert words[0] in ADJECTIVES
    assert words[1] in NOUNS


def test_generate_memorable_name_randomness():
    """Test that the function generates different names."""
    names = {generate_memorable_name() for _ in range(100)}

    # With hundreds of adjectives and nouns, 100 draws should produce close to
    # 100 unique names. Keep a conservative lower bound to tolerate randomness.
    assert len(names) > 90


def test_generate_memorable_name_string_type():
    """Test that the generated name is a string."""
    name = generate_memorable_name()
    assert isinstance(name, str)


def test_word_lists_not_empty():
    """Test that our word lists contain entries."""
    assert len(ADJECTIVES) > 0
    assert len(NOUNS) > 0


def test_word_lists_are_strings():
    """Test that all entries in word lists are strings."""
    assert all(isinstance(word, str) for word in ADJECTIVES)
    assert all(isinstance(word, str) for word in NOUNS)


def test_word_lists_no_duplicates():
    """Test that word lists don't contain duplicates."""
    assert len(ADJECTIVES) == len(set(ADJECTIVES))
    assert len(NOUNS) == len(set(NOUNS))


def test_word_lists_are_single_capitalized_words():
    """Test that each entry is a single capitalized word with no whitespace."""
    for word in ADJECTIVES:
        assert word and word[0].isupper()
        assert " " not in word
    for word in NOUNS:
        assert word and word[0].isupper()
        assert " " not in word
