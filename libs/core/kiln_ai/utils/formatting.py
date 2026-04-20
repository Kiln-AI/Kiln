import re

AGENT_TRUNCATION_SENTINEL = "[...truncated, load task for full instructions]"


def snake_case(s: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", s).lower()


def truncate_to_words(text: str | None, max_words: int) -> tuple[str | None, bool]:
    """Truncate text to a maximum number of words.

    Returns a tuple of (truncated_text, was_truncated).
    If text is None, returns (None, False).
    """
    if text is None:
        return None, False
    words = text.split()
    if len(words) <= max_words:
        return text, False
    return " ".join(words[:max_words]) + " \u2026", True


def truncate_to_words_with_agent_sentinel(
    text: str | None, max_words: int
) -> str | None:
    """Truncate to max_words and append AGENT_TRUNCATION_SENTINEL when truncation
    occurred. Preserves None for None. Applied to task instructions surfaced to
    the LLM agent -- see specs/projects/agent_info_trim."""
    truncated, was_truncated = truncate_to_words(text, max_words)
    if not was_truncated:
        return truncated
    # truncated is guaranteed non-None (and non-empty) when was_truncated is True
    assert truncated is not None
    stripped = truncated.removesuffix(" \u2026").rstrip()
    if not stripped:
        return AGENT_TRUNCATION_SENTINEL
    return f"{stripped} {AGENT_TRUNCATION_SENTINEL}"
