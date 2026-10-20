import asyncio
import re
import time
from unittest.mock import patch

import pytest
import regex

from kiln_ai.adapters.eval.trace_tools.v1.conftest import golden_trace
from kiln_ai.adapters.eval.trace_tools.v1.errors import TraceToolUsageError
from kiln_ai.adapters.eval.trace_tools.v1.limits import RESPONSE_CHARS
from kiln_ai.adapters.eval.trace_tools.v1.render import TextArgs, read_message_text
from kiln_ai.adapters.eval.trace_tools.v1.search import SearchArgs, search_trace
from kiln_ai.adapters.eval.trace_tools.v1.view import build_view


def _view(*contents, role="user"):
    return build_view([{"role": role, "content": c} for c in contents])


def _hits(output: str) -> list[str]:
    return [line for line in output.splitlines() if line.startswith("#")]


@pytest.mark.parametrize(
    "regex, expected",
    [
        (False, ["#2 user content @2"]),
        (True, ["#1 user content @0", "#2 user content @2"]),
    ],
)
def test_search_literal_vs_regex(regex, expected):
    view = _view("abc", "x a.c")
    assert _hits(search_trace(view, SearchArgs(pattern="a.c", regex=regex))) == expected


@pytest.mark.parametrize(
    "case_sensitive, expected",
    [
        (False, ["#1 user content @0", "#1 user content @6"]),
        (True, ["#1 user content @6"]),
    ],
)
def test_search_case_sensitivity(case_sensitive, expected):
    view = _view("Error error")
    args = SearchArgs(pattern="error", case_sensitive=case_sensitive)
    assert _hits(search_trace(view, args)) == expected


def test_search_offsets_match_read_message_text(coding_view):
    output = search_trace(
        coding_view,
        SearchArgs(
            pattern="Decimal",
            case_sensitive=True,
            parts=("content", "reasoning", "tool_calls"),
            count=1_000,
        ),
    )
    hits = _hits(output)
    assert len(hits) > 10
    for hit in hits:
        match = re.fullmatch(r"#(\d+) .* (content|reasoning|tool_calls) @(\d+)", hit)
        assert match is not None
        number, part = int(match.group(1)), match.group(2)
        offset = int(match.group(3))
        window = read_message_text(
            coding_view,
            TextArgs(number=number, part=part, offset=offset, max_chars=7),  # type: ignore[arg-type]
        )
        assert window.splitlines()[1] == "Decimal"


@pytest.mark.parametrize(
    "pattern, context_chars, expected",
    [
        ("abc", 3, '#1 user content @0: "abcdef" <truncated>'),
        ("xyz", 3, '#1 user content @16: <truncated> "uvwxyz"'),
        ("ghi", 3, '#1 user content @6: <truncated> "defghijkl" <truncated>'),
        ("abc", 100, '#1 user content @0: "abcdefghijkl\\nuvwxyz"'),
    ],
)
def test_search_context_snippet_edges(pattern, context_chars, expected):
    view = _view("abcdefghijkl\nuvwxyz")
    output = search_trace(
        view, SearchArgs(pattern=pattern, context_chars=context_chars)
    )
    assert _hits(output) == [expected]


def test_search_tool_result_label():
    view = build_view(
        [
            {
                "role": "assistant",
                "tool_calls": [
                    {"id": "a", "function": {"name": "grep", "arguments": "{}"}}
                ],
            },
            {"role": "tool", "tool_call_id": "a", "content": "needle"},
        ]
    )
    assert _hits(search_trace(view, SearchArgs(pattern="needle"))) == [
        "#2 tool grep content @0"
    ]


def test_search_paging_count_offset():
    view = _view("x x x", "x", "x x")
    first_page = search_trace(view, SearchArgs(pattern="x", count=2))
    assert first_page.splitlines() == [
        "6 matches in 3 messages. Showing matches 1\u20132.",
        "#1 user content @0",
        "#1 user content @2",
        "Use offset=2 for more.",
    ]
    last_page = search_trace(view, SearchArgs(pattern="x", count=3, offset=4))
    assert last_page.splitlines() == [
        "6 matches in 3 messages. Showing matches 5\u20136.",
        "#3 user content @0",
        "#3 user content @2",
    ]
    with pytest.raises(TraceToolUsageError) as e:
        search_trace(view, SearchArgs(pattern="x", offset=6))
    assert str(e.value) == "offset 6 is past the last match (6 matches)."


def test_search_positions_and_offsets_are_plain_integers():
    view = _view("x" * 1_500 + "needle")
    assert _hits(search_trace(view, SearchArgs(pattern="needle"))) == [
        "#1 user content @1500"
    ]
    with pytest.raises(TraceToolUsageError) as e:
        search_trace(view, SearchArgs(pattern="needle", offset=1_000))
    assert str(e.value) == "offset 1000 is past the last match (1 match)."


def test_search_singular_counts():
    assert search_trace(_view("x"), SearchArgs(pattern="x")).splitlines()[0] == (
        "1 match in 1 message. Showing matches 1\u20131."
    )


def test_search_zero_length_matches_skipped():
    output = search_trace(_view("axxb", "b"), SearchArgs(pattern="x*", regex=True))
    assert _hits(output) == ["#1 user content @1"]


def test_search_no_matches():
    assert (
        search_trace(_view("abc"), SearchArgs(pattern='q"z'))
        == 'No matches for "q\\"z".'
    )


def test_search_invalid_regex():
    with pytest.raises(TraceToolUsageError) as e:
        search_trace(_view("abc"), SearchArgs(pattern="[a-", regex=True))
    assert str(e.value).startswith("Invalid regex: ")
    assert str(e.value).endswith(". Use regex=false to search plain text.")


def test_search_literal_mode_never_fails_to_compile():
    output = search_trace(_view("a [a- b"), SearchArgs(pattern="[a-"))
    assert _hits(output) == ["#1 user content @2"]


def test_search_timeout():
    view = _view("a" * 40 + "b")
    with pytest.raises(TraceToolUsageError) as e:
        search_trace(
            view, SearchArgs(pattern="(a|aa)+$", regex=True), timeout_seconds=0.01
        )
    assert str(e.value) == (
        "Search timed out after 0.01 seconds. Use a simpler pattern, or narrow it "
        "with start/end, roles or parts."
    )


def test_search_timeout_across_many_small_parts():
    # Each part takes well under a millisecond, so only a deadline check between
    # parts stops this search.
    view = _view(*(["a" * 12 + "!"] * 3_000))
    with pytest.raises(
        TraceToolUsageError, match=r"^Search timed out after 0\.01 seconds\."
    ):
        search_trace(
            view, SearchArgs(pattern="(a|aa)+$", regex=True), timeout_seconds=0.01
        )


async def test_regex_search_releases_the_gil_while_matching():
    view = _view("a" * 40 + "b")
    ticks = 0

    async def tick():
        nonlocal ticks
        while True:
            await asyncio.sleep(0.05)
            ticks += 1

    ticker = asyncio.create_task(tick())
    with pytest.raises(TraceToolUsageError, match=r"^Search timed out"):
        await asyncio.to_thread(
            search_trace,
            view,
            SearchArgs(pattern="(a|aa)+$", regex=True),
            timeout_seconds=1,
        )
    ticker.cancel()
    assert ticks >= 10


def test_search_rejects_huge_counted_repeat_quickly():
    started = time.perf_counter()
    with pytest.raises(TraceToolUsageError, match=r"^Pattern too large: "):
        search_trace(_view("aaa"), SearchArgs(pattern="a{100000000}", regex=True))
    assert time.perf_counter() - started < 0.5


def test_search_literal_braces_are_not_repeats():
    output = search_trace(_view("a{100000000}"), SearchArgs(pattern="a{100000000}"))
    assert _hits(output) == ["#1 user content @0"]


def test_search_rejects_verbose_mode():
    with pytest.raises(
        TraceToolUsageError, match=r"^Verbose mode \(\?x\) and full case folding"
    ):
        search_trace(_view("a"), SearchArgs(pattern="(?x)a", regex=True))


def test_search_deeply_nested_groups_are_invalid():
    pattern = "(" * 5_000 + "a" + ")" * 5_000
    with pytest.raises(TraceToolUsageError) as e:
        search_trace(_view("a"), SearchArgs(pattern=pattern, regex=True))
    assert str(e.value) == (
        "Invalid regex: groups are nested too deeply. Use regex=false to search plain text."
    )


def test_search_does_not_cache_compiled_patterns():
    with patch(
        "kiln_ai.adapters.eval.trace_tools.v1.search.regex.compile",
        wraps=regex.compile,
    ) as compile_spy:
        search_trace(_view("abc"), SearchArgs(pattern="a"))
        search_trace(_view("abc"), SearchArgs(pattern="a", regex=True))
    assert [c.kwargs.get("cache_pattern") for c in compile_spy.call_args_list] == [
        False,
        False,
    ]


def test_search_empty_pattern():
    with pytest.raises(TraceToolUsageError, match=r"^pattern must not be empty\.$"):
        search_trace(_view("abc"), SearchArgs(pattern=""))


def test_search_part_order_and_filters():
    view = build_view(
        [
            {
                "role": "assistant",
                "content": "match",
                "reasoning_content": "match",
                "tool_calls": [
                    {"id": "a", "function": {"name": "match", "arguments": "{}"}}
                ],
            },
            {"role": "user", "content": "match"},
            {"role": "user", "content": "match"},
        ]
    )
    assert _hits(search_trace(view, SearchArgs(pattern="match"))) == [
        "#1 assistant content @0",
        "#1 assistant tool_calls @0",
        "#2 user content @0",
        "#3 user content @0",
    ]
    all_parts = SearchArgs(
        pattern="match", parts=("tool_calls", "content", "reasoning"), end=1
    )
    assert _hits(search_trace(view, all_parts)) == [
        "#1 assistant reasoning @0",
        "#1 assistant content @0",
        "#1 assistant tool_calls @0",
    ]
    filtered = SearchArgs(pattern="match", roles=("user",), start=3)
    assert _hits(search_trace(view, filtered)) == ["#3 user content @0"]


@pytest.mark.parametrize(
    "args, message",
    [
        (SearchArgs(pattern="x", start=4), "Message #4 doesn't exist."),
        (SearchArgs(pattern="x", start=3, end=2), "start (3) is after end (2)."),
        (SearchArgs(pattern="x", roles=("robot",)), 'Unknown role "robot".'),
    ],
)
def test_search_argument_errors(args, message):
    with pytest.raises(TraceToolUsageError, match=f"^{re.escape(message)}"):
        search_trace(_view("x", "x", "x"), args)


@pytest.mark.parametrize("found_matches_after_page", [True, False])
def test_search_refusal_count_fits(found_matches_after_page):
    view = build_view(golden_trace("synthetic"))
    args = SearchArgs(pattern="value_", count=500, context_chars=60)
    total = int(
        search_trace(view, SearchArgs(pattern="value_", count=1))
        .split()[0]
        .replace(",", "")
    )
    if not found_matches_after_page:
        args = SearchArgs(
            pattern="value_", count=500, context_chars=60, offset=total - 500
        )
    with pytest.raises(TraceToolUsageError) as e:
        search_trace(view, args)
    match = re.search(r"\ncount=(\d+) fits at these settings\.\n", str(e.value))
    assert match is not None
    fitting = int(match.group(1))
    narrowed = SearchArgs(
        pattern="value_", count=fitting, context_chars=60, offset=args.offset
    )
    assert len(search_trace(view, narrowed)) <= RESPONSE_CHARS
    widened = SearchArgs(
        pattern="value_", count=fitting + 1, context_chars=60, offset=args.offset
    )
    with pytest.raises(TraceToolUsageError):
        search_trace(view, widened)
