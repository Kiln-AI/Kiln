import re


def clean_up_text(text: str) -> str:
    """
    Clean up text by removing consecutive newlines and consecutive whitespace. Models sometimes send a lot of those.
    It seems to happen more when the transcription is done at low temperature.
    """
    text = re.sub(r"\n+", "\n", text)
    text = re.sub(" +", " ", text)
    return text.strip()
