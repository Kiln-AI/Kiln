from kiln_ai.utils.formatting import (
    AGENT_TRUNCATION_SENTINEL,
    truncate_to_words,
    truncate_to_words_with_agent_sentinel,
)


def test_agent_truncation_sentinel_value():
    assert (
        AGENT_TRUNCATION_SENTINEL == "[...truncated, load task for full instructions]"
    )


def test_sentinel_under_limit():
    result = truncate_to_words_with_agent_sentinel("hello world", 10)
    assert result == "hello world"


def test_sentinel_at_limit():
    words = " ".join(f"word{i}" for i in range(10))
    result = truncate_to_words_with_agent_sentinel(words, 10)
    assert result == words


def test_sentinel_over_limit():
    words = " ".join(f"word{i}" for i in range(15))
    result = truncate_to_words_with_agent_sentinel(words, 10)
    expected_prefix = " ".join(f"word{i}" for i in range(10))
    assert result == f"{expected_prefix} {AGENT_TRUNCATION_SENTINEL}"


def test_sentinel_one_over_limit():
    words = " ".join(f"word{i}" for i in range(11))
    result = truncate_to_words_with_agent_sentinel(words, 10)
    expected_prefix = " ".join(f"word{i}" for i in range(10))
    assert result == f"{expected_prefix} {AGENT_TRUNCATION_SENTINEL}"


def test_sentinel_none_input():
    result = truncate_to_words_with_agent_sentinel(None, 10)
    assert result is None


def test_sentinel_empty_string():
    result = truncate_to_words_with_agent_sentinel("", 10)
    assert result == ""


def test_sentinel_no_double_spaces_at_cut_point():
    text = "word1 word2  word3  word4 word5 word6"
    result = truncate_to_words_with_agent_sentinel(text, 3)
    assert "  " not in result
    assert result == f"word1 word2 word3 {AGENT_TRUNCATION_SENTINEL}"


def test_sentinel_appears_exactly_once():
    words = " ".join(f"word{i}" for i in range(200))
    result = truncate_to_words_with_agent_sentinel(words, 5)
    assert result is not None
    assert result.count(AGENT_TRUNCATION_SENTINEL) == 1


def test_sentinel_not_present_when_not_truncated():
    result = truncate_to_words_with_agent_sentinel("short text", 100)
    assert result is not None
    assert AGENT_TRUNCATION_SENTINEL not in result


def test_sentinel_max_words_zero():
    result = truncate_to_words_with_agent_sentinel("hello world", 0)
    assert result == AGENT_TRUNCATION_SENTINEL


def test_sentinel_max_words_one():
    result = truncate_to_words_with_agent_sentinel("hello world foo", 1)
    assert result == f"hello {AGENT_TRUNCATION_SENTINEL}"


# --- truncate_to_words tests ---


def test_truncate_to_words_empty():
    text, truncated = truncate_to_words("", 10)
    assert text == ""
    assert truncated is False


def test_truncate_to_words_under_limit():
    text, truncated = truncate_to_words("hello world", 10)
    assert text == "hello world"
    assert truncated is False


def test_truncate_to_words_at_limit():
    words = " ".join(f"word{i}" for i in range(10))
    text, truncated = truncate_to_words(words, 10)
    assert text == words
    assert truncated is False


def test_truncate_to_words_one_over():
    words = " ".join(f"word{i}" for i in range(11))
    text, truncated = truncate_to_words(words, 10)
    expected = " ".join(f"word{i}" for i in range(10)) + " \u2026"
    assert text == expected
    assert truncated is True


def test_truncate_to_words_over_limit():
    words = " ".join(f"w{i}" for i in range(200))
    text, truncated = truncate_to_words(words, 5)
    expected = " ".join(f"w{i}" for i in range(5)) + " \u2026"
    assert text == expected
    assert truncated is True


def test_truncate_to_words_normalizes_whitespace():
    text, truncated = truncate_to_words("a  b\tc\nd  e  f  g", 5)
    assert text == "a b c d e \u2026"
    assert truncated is True


def test_truncate_to_words_none():
    text, truncated = truncate_to_words(None, 10)
    assert text is None
    assert truncated is False
