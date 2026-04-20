import re

AGENT_TRUNCATION_SENTINEL = "[...truncated, load task for full instructions]"


def snake_case(s: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", s).lower()


def truncate_to_words_with_agent_sentinel(
    text: str | None, max_words: int
) -> str | None:
    """Truncate to max_words and append AGENT_TRUNCATION_SENTINEL when truncation
    occurred. Preserves None for None. Preserves original whitespace in the
    retained prefix. Applied to task instructions surfaced to the LLM agent --
    see specs/projects/agent_info_trim."""
    if max_words < 0:
        raise ValueError("max_words must be non-negative")
    if text is None:
        return None
    words = text.split()
    if len(words) <= max_words:
        return text
    # Find the end position of the max_words-th word in the original text,
    # preserving original whitespace in the prefix.
    pos = 0
    for _ in range(max_words):
        # Skip whitespace
        while pos < len(text) and text[pos].isspace():
            pos += 1
        # Skip word
        while pos < len(text) and not text[pos].isspace():
            pos += 1
    prefix = text[:pos].rstrip()
    if not prefix:
        return AGENT_TRUNCATION_SENTINEL
    return f"{prefix} {AGENT_TRUNCATION_SENTINEL}"
