import re


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
