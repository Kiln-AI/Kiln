"""The YAML front matter at the top of a skill file, between two `---` lines."""

from dataclasses import dataclass, field

import yaml

FENCE = "---"


@dataclass(frozen=True)
class FrontMatter:
    present: bool
    """The file starts with a `---` line."""
    data: dict[str, object] = field(default_factory=dict)
    """Empty when `error` is set."""
    error: str | None = None
    body: str = ""
    """The text after the closing `---` line; the whole text when there is no
    closed block."""


def read_front_matter(text: str) -> FrontMatter:
    lines = text.split("\n")
    if lines[0] != FENCE:
        return FrontMatter(present=False, body=text)
    try:
        end = lines.index(FENCE, 1)
    except ValueError:
        return FrontMatter(present=True, error="front matter is not closed", body=text)
    body = "\n".join(lines[end + 1 :])
    try:
        loaded = yaml.safe_load("\n".join(lines[1:end]))
    # The YAML loader raises ValueError for an impossible date such as 2026-02-30.
    except (yaml.YAMLError, ValueError) as error:
        return FrontMatter(
            present=True, error=f"front matter is not valid YAML: {error}", body=body
        )
    if not isinstance(loaded, dict):
        return FrontMatter(present=True, error="front matter is not a map", body=body)
    return FrontMatter(
        present=True, data={str(key): value for key, value in loaded.items()}, body=body
    )
