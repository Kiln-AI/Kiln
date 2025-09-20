import re


def clean_up_text(text: str) -> str:
    """
    Clean up text by limiting consecutive newlines and consecutive whitespace. Models sometimes send a lot of those.
    It seems to happen more when the transcription is done at low temperature.

    - Replaces 6+ consecutive newlines with exactly 6 newlines
    - Replaces 50+ consecutive spaces with exactly 50 spaces
    - Leaves 1-5 consecutive newlines unchanged
    - Leaves 1-49 consecutive spaces unchanged
    """
    max_consecutive_newlines = 6
    max_consecutive_whitespace = 50

    # Replace 6+ consecutive newlines with exactly 6 newlines
    text = re.sub(r"\n{6,}", "\n" * max_consecutive_newlines, text)

    # Replace 50+ consecutive spaces with exactly 50 spaces
    text = re.sub(r" {50,}", " " * max_consecutive_whitespace, text)

    return text.strip()
