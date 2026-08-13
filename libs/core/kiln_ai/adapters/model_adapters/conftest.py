"""Shared fixtures for the model adapter tests."""

from typing import Any, Callable, Sequence

import pytest


@pytest.fixture
def nudges_in() -> Callable[[Sequence[Any]], list[str]]:
    """Return the contents of the stuck-loop nudges Kiln injected into a message list.

    Shared by the blocking and streaming tool-loop suites so both assert on the same
    thing: a message the adapter added itself, marked with `kiln_injected`.
    """

    def _nudges_in(messages: Sequence[Any]) -> list[str]:
        return [
            str(message["content"])
            for message in messages
            if isinstance(message, dict) and message.get("kiln_injected")
        ]

    return _nudges_in
