"""Numeric limits of trace toolset v1.

Part of the frozen toolset: changing a value changes tool output, so it needs a
new toolset version.
"""

__all__ = [
    "MAX_CHARS_MAX",
    "NAME_CHARS",
    "NUMBERS_MAX_ITEMS",
    "OVERVIEW_LARGEST",
    "OVERVIEW_OTHER_ROLES",
    "OVERVIEW_PREVIEW_CHARS",
    "OVERVIEW_TOP_TOOLS",
    "PREVIEW_CHARS_DEFAULT",
    "PREVIEW_CHARS_MAX",
    "READ_MAX_CHARS_DEFAULT",
    "RESPONSE_CHARS",
    "SEARCH_CONTEXT_DEFAULT",
    "SEARCH_CONTEXT_MAX",
    "SEARCH_COUNT_DEFAULT",
    "SEARCH_COUNT_MAX",
    "SEARCH_PATTERN_ELEMENTS_MAX",
    "SEARCH_TIMEOUT_SECONDS",
    "TEXT_MAX_CHARS_DEFAULT",
]

RESPONSE_CHARS = 40_000
"""The most characters any tool response may have. Larger responses are refused."""

PREVIEW_CHARS_DEFAULT = 80
"""Default ``preview_chars`` of ``preview_messages``."""
PREVIEW_CHARS_MAX = 1_000
"""Largest ``preview_chars`` of ``preview_messages``."""

READ_MAX_CHARS_DEFAULT = 1_000
"""Default ``max_chars`` of ``read_messages``, applied to each part."""
TEXT_MAX_CHARS_DEFAULT = 2_000
"""Default ``max_chars`` of ``read_message_text``."""
MAX_CHARS_MAX = 40_000
"""Largest ``max_chars`` of ``read_messages`` and ``read_message_text``."""
NUMBERS_MAX_ITEMS = 1_000
"""Most message numbers one ``read_messages`` call may list."""

SEARCH_COUNT_DEFAULT = 100
"""Default ``count`` (matches per page) of ``search_trace``."""
SEARCH_COUNT_MAX = 1_000
"""Largest ``count`` of ``search_trace``."""
SEARCH_CONTEXT_DEFAULT = 0
"""Default ``context_chars`` of ``search_trace``."""
SEARCH_CONTEXT_MAX = 2_000
"""Largest ``context_chars`` of ``search_trace``."""
SEARCH_TIMEOUT_SECONDS = 30
"""How long one ``search_trace`` call may spend matching."""
SEARCH_PATTERN_ELEMENTS_MAX = 100_000
"""The most elements a regex search pattern may be estimated to compile to."""

OVERVIEW_PREVIEW_CHARS = 300
"""Length of the first-user and last-assistant previews in ``trace_overview``."""
OVERVIEW_TOP_TOOLS = 20
"""Most tool names listed in ``trace_overview``."""
OVERVIEW_LARGEST = 5
"""Number of largest messages listed in ``trace_overview``."""
OVERVIEW_OTHER_ROLES = 5
"""Most rows ``trace_overview`` gives roles outside the standard five."""

NAME_CHARS = 60
"""Role and tool names longer than this are cut where they are shown in labels."""
