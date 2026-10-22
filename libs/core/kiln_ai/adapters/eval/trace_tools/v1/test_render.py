import re

import pytest

from kiln_ai.adapters.eval.trace_tools.v1.conftest import golden_trace
from kiln_ai.adapters.eval.trace_tools.v1.errors import TraceToolUsageError
from kiln_ai.adapters.eval.trace_tools.v1.limits import MAX_CHARS_MAX, RESPONSE_CHARS
from kiln_ai.adapters.eval.trace_tools.v1.render import (
    PreviewArgs,
    ReadArgs,
    RefusalContext,
    TextArgs,
    Unit,
    approx_tokens,
    assemble,
    fmt_count,
    preview_messages,
    quote,
    read_message_text,
    read_messages,
    render_overview,
)
from kiln_ai.adapters.eval.trace_tools.v1.view import build_view

MARKER = re.compile(
    r"<truncated: ([\d,]+) more chars; "
    r"read_message_text\(number=(\d+), part=(\w+), offset=(\d+)\)>"
)


def _call(call_id, name, arguments="{}"):
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": arguments},
    }


def _users(*contents):
    return build_view([{"role": "user", "content": c} for c in contents])


@pytest.mark.parametrize(
    "chars, expected",
    [
        (0, "~0"),
        (3_996, "~999"),
        (4_000, "~1k"),
        (2_104_330, "~526k"),
        (4_800_000, "~1.2M"),
    ],
)
def test_approx_tokens_buckets(chars, expected):
    assert approx_tokens(chars) == expected


@pytest.mark.parametrize(
    "args, expected",
    [
        ((0, "error"), "0 errors"),
        ((1, "message"), "1 message"),
        ((1_284, "message"), "1,284 messages"),
        ((1, "match", "matches"), "1 match"),
        ((3, "match", "matches"), "3 matches"),
    ],
)
def test_fmt_count(args, expected):
    assert fmt_count(*args) == expected


@pytest.mark.parametrize(
    "text, max_chars, expected",
    [
        ('a\nb"c\\d\te', 100, '"a\\nb\\"c\\\\d\\te"'),
        ("abcdef", 3, '"abc" <truncated>'),
        ("abc", 3, '"abc"'),
        ("café", 10, '"café"'),
    ],
)
def test_quote_escaping_and_truncated_marker(text, max_chars, expected):
    assert quote(text, max_chars) == expected
    assert "…" not in quote(text, max_chars)


def test_overview_format():
    view = build_view(
        [
            {"role": "system", "content": "s" * 10},
            {"role": "user", "content": "Do the thing."},
            {
                "role": "assistant",
                "content": "On it.",
                "reasoning_content": "r" * 1_500,
                "tool_calls": [
                    _call("a", "read"),
                    _call("b", "read"),
                    _call("c", "grep"),
                ],
            },
            {"role": "tool", "tool_call_id": "a", "content": "x" * 12_345},
            {"role": "tool", "tool_call_id": "b", "content": "y", "is_error": True},
            {"role": "tool", "tool_call_id": "c", "content": "z", "is_error": True},
            {"role": "assistant", "content": "Done."},
        ]
    )
    assert render_overview(view) == "\n".join(
        [
            "Trace: 7 messages, 13,904 chars (~3k tokens)",
            "  system    1     10 chars",
            "  user      1     13 chars",
            "  assistant 2     34 chars (+1,500 reasoning), 3 tool calls",
            "  tool      3 12,347 chars, 2 errors",
            "Tool calls: read \u00d72, grep \u00d71",
            "Largest messages: #4 tool read 12,345 · #3 assistant 1,529 · "
            "#2 user 13 · #1 system 10 · #7 assistant 5",
            'First user message (#2, 13 chars): "Do the thing."',
            'Last assistant message with text (#7, 5 chars): "Done."',
        ]
    )


def test_overview_empty_trace():
    assert render_overview(build_view([])) == "Trace: 0 messages, 0 chars (~0 tokens)"


def test_overview_top_tools_overflow():
    calls = [_call(f"{i}", f"tool_{i:02d}") for i in range(22)] + [
        _call("x", "tool_21"),
        _call("y", "tool_05"),
    ]
    view = build_view([{"role": "assistant", "tool_calls": calls}])
    tool_line = next(
        line
        for line in render_overview(view).splitlines()
        if line.startswith("Tool calls: ")
    )
    listed = tool_line.removeprefix("Tool calls: ").split(", ")
    assert listed[:3] == ["tool_05 \u00d72", "tool_21 \u00d72", "tool_00 \u00d71"]
    assert len(listed) == 21
    assert listed[-1] == "+2 more tools"


def test_overview_omits_lines_without_data():
    overview = render_overview(
        build_view(
            [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": ""},
                {"role": "assistant", "content": None},
            ]
        )
    )
    assert "Tool calls:" not in overview
    assert "First user message" not in overview
    assert "Last assistant message" not in overview
    assert "  developer" not in overview
    assert overview.splitlines()[-1].startswith("Largest messages: #1 system 3")


def test_overview_largest_ties_by_number():
    overview = render_overview(_users("aa", "b", "cc", "dd", "ee", "ff", "gg"))
    assert (
        "Largest messages: #1 user 2 · #3 user 2 · #4 user 2 · #5 user 2 · #6 user 2"
    ) in overview


def test_overview_caps_other_role_rows():
    view = build_view(
        [{"role": f"role_{i}", "content": "x"} for i in range(7)]
        + [{"role": "user", "content": "hi"}]
    )
    rows = [
        line for line in render_overview(view).splitlines() if line.startswith("  ")
    ]
    assert [row.split()[0] for row in rows] == [
        "user",
        "role_0",
        "role_1",
        "role_2",
        "role_3",
        "role_4",
        "+2",
    ]
    assert rows[-1] == "  +2 more roles"


def test_long_names_are_cut_in_labels():
    long_name = "t" * 100
    view = build_view(
        [
            {"role": "r" * 100, "content": "x"},
            {"role": "assistant", "tool_calls": [_call("a", long_name)]},
            {"role": "tool", "tool_call_id": "a", "content": "result"},
        ]
    )
    cut = "t" * 60 + "\u2026"
    overview = render_overview(view)
    assert f"  {'r' * 60}\u2026 1 " in overview
    assert f"Tool calls: {cut} \u00d71" in overview
    assert f"#3 tool {cut} 6" in overview
    preview = preview_messages(view, PreviewArgs(preview_chars=0)).splitlines()
    assert preview[1] == f"#2 assistant 0, calls {cut} (103)"
    assert preview[2] == f"#3 tool {cut} 6"
    assert read_message_text(view, TextArgs(number=3)).startswith(
        f"=== #3 tool result from {cut} \u2014"
    )
    call_line = read_messages(view, ReadArgs(numbers=(2,))).splitlines()[1]
    assert call_line.startswith(f"[call] {long_name} {{}}")


def test_overview_bounded_for_pathological_traces():
    view = build_view(
        [{"role": f"{i}" * 1_000, "content": "x"} for i in range(2_000)]
        + [
            {
                "role": "assistant",
                "content": "\u0000" * 1_000,
                "tool_calls": [_call(f"{i}", f"{i}" * 1_000) for i in range(2_000)],
            },
            {"role": "user", "content": "\u0001" * 1_000},
        ]
    )
    assert len(render_overview(view)) < 10_000


def test_overview_preview_cut_at_300_chars():
    overview = render_overview(_users("q" * 301))
    assert f'First user message (#1, 301 chars): "{"q" * 300}" <truncated>' in overview


@pytest.mark.parametrize(
    "message, preview_chars, expected",
    [
        ({"role": "user", "content": "hi"}, 80, '#1 user 2: "hi"'),
        ({"role": "user", "content": "hello"}, 3, '#1 user 5: "hel" <truncated>'),
        ({"role": "user", "content": "hello"}, 0, "#1 user 5"),
        ({"role": "user", "content": ""}, 80, "#1 user 0"),
        (
            {"role": "assistant", "content": "ok", "reasoning_content": "r" * 1_840},
            80,
            '#1 assistant 2 (+1,840 reasoning): "ok"',
        ),
        (
            {
                "role": "assistant",
                "tool_calls": [
                    _call("a", "edit"),
                    _call("b", "read"),
                    _call("c", "edit"),
                ],
            },
            80,
            "#1 assistant 0, calls edit \u00d72, read (23)",
        ),
        (
            {"role": "tool", "tool_call_id": "x", "content": "boom", "is_error": True},
            80,
            '#1 tool unknown tool 4 ERROR: "boom"',
        ),
    ],
)
def test_preview_line_pieces(message, preview_chars, expected):
    assert (
        preview_messages(
            build_view([message]), PreviewArgs(preview_chars=preview_chars)
        )
        == expected
    )


def test_preview_range_and_roles(coding_view):
    lines = preview_messages(
        coding_view, PreviewArgs(start=3, end=5, roles=("tool",), preview_chars=0)
    ).splitlines()
    assert lines == ["#4 tool read_file 1,353", "#5 tool grep 33 ERROR"]


def test_preview_no_match(coding_view):
    assert (
        preview_messages(
            coding_view, PreviewArgs(start=4, end=5, roles=("user", "system"))
        )
        == "No messages match (#4\u2013#5, roles: user, system)."
    )


@pytest.mark.parametrize(
    "start, end, message",
    [
        (0, None, "Message #0 doesn't exist. The trace has 16 messages (#1\u2013#16)."),
        (
            None,
            17,
            "Message #17 doesn't exist. The trace has 16 messages (#1\u2013#16).",
        ),
        (5, 4, "start (5) is after end (4)."),
    ],
)
def test_range_errors(coding_view, start, end, message):
    with pytest.raises(TraceToolUsageError) as e:
        preview_messages(coding_view, PreviewArgs(start=start, end=end))
    assert str(e.value) == message


def test_range_error_on_empty_trace():
    with pytest.raises(TraceToolUsageError, match=r"^The trace has no messages\.$"):
        preview_messages(build_view([]), PreviewArgs())


def test_preview_single_message_range(coding_view):
    assert preview_messages(
        coding_view, PreviewArgs(start=16, end=16, preview_chars=0)
    ) == ("#16 assistant 204")


@pytest.mark.parametrize(
    "render",
    [
        lambda view: preview_messages(view, PreviewArgs(roles=("robot",))),
        lambda view: read_messages(view, ReadArgs(parts=("bogus",))),  # type: ignore[arg-type]
        lambda view: read_message_text(view, TextArgs(number=1, part="bogus")),  # type: ignore[arg-type]
    ],
)
def test_unknown_filter_values(coding_view, render):
    with pytest.raises(
        TraceToolUsageError, match=r'^Unknown (role|part) "(robot|bogus)"\. Valid '
    ):
        render(coding_view)


def _block_headers(output: str) -> list[str]:
    return [line for line in output.splitlines() if line.startswith("=== ")]


def test_read_selection_requires_requested_part(coding_view):
    output = read_messages(
        coding_view, ReadArgs(roles=("assistant",), parts=("content",))
    )
    assert [h.split()[1] for h in _block_headers(output)] == ["#3", "#10", "#12", "#16"]
    assert "Not shown" not in output


def test_read_numbers_footer_reasons(coding_view):
    output = read_messages(
        coding_view,
        ReadArgs(numbers=(7, 1, 7, 6), roles=("assistant", "tool"), parts=("content",)),
    )
    assert _block_headers(output) == [
        "=== #7 tool result from edit_file (content 29) ==="
    ]
    assert output.endswith(
        "\nNot shown: #1 (role not in roles), #6 (no requested parts)"
    )


def test_read_numbers_and_range_conflict(coding_view):
    with pytest.raises(TraceToolUsageError, match=r"^Use either numbers or start/end"):
        read_messages(coding_view, ReadArgs(numbers=(1,), end=3))


def test_read_numbers_out_of_range(coding_view):
    with pytest.raises(TraceToolUsageError, match=r"^Message #99 doesn't exist"):
        read_messages(coding_view, ReadArgs(numbers=(1, 99)))


def test_read_no_match(coding_view):
    assert (
        read_messages(coding_view, ReadArgs(roles=("developer",)))
        == "No messages match (#1\u2013#16, roles: developer)."
    )


def test_read_header_sizes_and_body_order(coding_view):
    output = read_messages(
        coding_view, ReadArgs(numbers=(3,), parts=("tool_calls", "content"))
    )
    assert output.splitlines()[:3] == [
        "=== #3 assistant (content 41; reasoning 150 not shown; tool_calls 96) ===",
        "I'll start by reading the billing module.",
        '[call] read_file {"path": "billing/invoice.py"} → #4 ok, 1,353 chars',
    ]
    with_reasoning = read_messages(
        coding_view, ReadArgs(numbers=(3,), parts=("content", "reasoning"))
    )
    assert with_reasoning.splitlines()[1:5] == [
        "[reasoning]",
        coding_view.message(3).reasoning,
        "[content]",
        "I'll start by reading the billing module.",
    ]


@pytest.mark.parametrize(
    "parts, max_chars, body",
    [
        (("content",), 1_000, ["Answer."]),
        (("reasoning",), 1_000, ["[reasoning]", "Thinking."]),
        (
            ("content", "reasoning"),
            1_000,
            ["[reasoning]", "Thinking.", "[content]", "Answer."],
        ),
        (
            ("content", "reasoning"),
            5,
            [
                "[reasoning]",
                "Think",
                "<truncated: 4 more chars; read_message_text(number=1, part=reasoning, offset=5)>",
                "[content]",
                "Answe",
                "<truncated: 2 more chars; read_message_text(number=1, part=content, offset=5)>",
            ],
        ),
    ],
)
def test_read_content_label_only_after_reasoning(parts, max_chars, body):
    view = build_view(
        [{"role": "assistant", "content": "Answer.", "reasoning_content": "Thinking."}]
    )
    output = read_messages(view, ReadArgs(parts=parts, max_chars=max_chars))
    assert output.splitlines()[1:] == body


def test_read_call_result_pointers(coding_view, edge_view):
    output = read_messages(coding_view, ReadArgs(numbers=(3,), parts=("tool_calls",)))
    assert output.splitlines()[1:] == [
        '[call] read_file {"path": "billing/invoice.py"} → #4 ok, 1,353 chars',
        '[call] grep {"pattern": "def total", "path": "billing/legacy"} → #5 ERROR, 33 chars',
    ]
    edge = read_messages(edge_view, ReadArgs(numbers=(12,), parts=("tool_calls",)))
    assert edge.splitlines()[1] == '[call] legacy_fn {"x": 1} → no result'


def _cut_calls_by_offset(message, max_chars):
    """The calls whose arguments are cut, keyed by where the cut falls in the
    tool_calls part."""
    cut_calls = {}
    line_start = 0
    for call in message.tool_calls:
        if len(call.arguments) > max_chars:
            cut_calls[line_start + len(call.name) + 1 + max_chars] = call
        line_start += len(f"{call.name} {call.arguments}") + 1
    return cut_calls


@pytest.mark.parametrize("max_chars", [1, 7, 60, 300])
def test_read_cut_markers_point_to_continuation(coding_view, max_chars):
    output = read_messages(
        coding_view,
        ReadArgs(parts=("reasoning", "content", "tool_calls"), max_chars=max_chars),
    )
    markers = list(MARKER.finditer(output))
    assert markers
    for marker in markers:
        remaining = int(marker.group(1).replace(",", ""))
        number, part, offset = (
            int(marker.group(2)),
            marker.group(3),
            int(marker.group(4)),
        )
        text = coding_view.part_text(number, part)  # type: ignore[arg-type]
        continuation = read_message_text(
            coding_view,
            TextArgs(number=number, part=part, offset=offset, max_chars=MAX_CHARS_MAX),  # type: ignore[arg-type]
        ).split("\n", 1)[1]
        assert continuation == text[offset:]
        if part == "tool_calls":
            call = _cut_calls_by_offset(coding_view.message(number), max_chars)[offset]
            assert remaining == len(call.arguments) - max_chars
            assert continuation.startswith(call.arguments[max_chars:])
        else:
            assert remaining == len(text) - max_chars
            assert offset == max_chars


def test_read_part_of_exactly_max_chars_has_no_marker():
    output = read_messages(_users("x" * 500), ReadArgs(max_chars=500))
    assert output == f"=== #1 user (content 500) ===\n{'x' * 500}"


def test_text_window_and_continuation(coding_view):
    assert read_message_text(
        coding_view, TextArgs(number=5, offset=30, max_chars=2)
    ) == (
        "=== #5 tool result from grep — content chars 30\u201332 of 33 ===\n"
        "ac\n"
        "<truncated: 1 more chars; read_message_text(number=5, part=content, offset=32)>"
    )
    assert read_message_text(coding_view, TextArgs(number=5, offset=32)).endswith(
        "chars 32\u201333 of 33 ===\ny"
    )
    whole = read_message_text(coding_view, TextArgs(number=4, max_chars=MAX_CHARS_MAX))
    assert whole.split("\n", 1)[1] == coding_view.message(4).content


@pytest.mark.parametrize(
    "args, message",
    [
        (
            TextArgs(number=4, part="reasoning"),
            "Message #4 has no reasoning. Its parts: content.",
        ),
        (
            TextArgs(number=6, part="content"),
            "Message #6 has no content. Its parts: tool_calls.",
        ),
        (
            TextArgs(number=5, offset=33),
            "offset 33 is past the end of #5 content (33 chars).",
        ),
        (
            TextArgs(number=4, offset=5_000),
            "offset 5000 is past the end of #4 content (1,353 chars).",
        ),
        (
            TextArgs(number=0),
            "Message #0 doesn't exist. The trace has 16 messages (#1\u2013#16).",
        ),
    ],
)
def test_text_errors(coding_view, args, message):
    with pytest.raises(TraceToolUsageError) as e:
        read_message_text(coding_view, args)
    assert str(e.value) == message


def test_text_empty_message():
    with pytest.raises(TraceToolUsageError, match=r"^Message #1 is empty\.$"):
        read_message_text(_users(""), TextArgs(number=1))


def _units(*sizes: int) -> list[Unit]:
    return [Unit(number, "x" * size) for number, size in enumerate(sizes, start=1)]


@pytest.mark.parametrize("last_size", [999, 1_000])
def test_refusal_just_under_limit_returns(last_size):
    units = _units(*([999] * 39), last_size)
    output = assemble(units, None, None, RefusalContext("range", "advice"))
    assert len(output) <= RESPONSE_CHARS


def test_refusal_fit_range_just_over_limit():
    units = _units(*([999] * 39), 1_001)
    with pytest.raises(TraceToolUsageError) as e:
        assemble(units, None, None, RefusalContext("range", "do less"))
    assert str(e.value) == (
        "Too large: this would return 40,001 chars, over the 40,000 limit. Nothing was returned.\n"
        "Messages #1\u2013#39 fit at these settings (start=1, end=39).\n"
        "To narrow it: do less."
    )


@pytest.mark.parametrize(
    "style, fit_line",
    [
        ("range", "Messages #1\u2013#2 fit at these settings (start=1, end=2)."),
        ("numbers", "The first 2 of the requested messages fit (through #2)."),
        ("matches", "count=2 fits at these settings."),
    ],
)
def test_refusal_fit_line_by_style(style, fit_line):
    units = _units(15_000, 15_000, 15_000)
    with pytest.raises(TraceToolUsageError) as e:
        assemble(units, None, None, RefusalContext(style, "advice"))
    assert str(e.value).splitlines()[1] == fit_line


@pytest.mark.parametrize(
    "style, fit_line",
    [
        ("range", "Even #1 alone is 40,001 chars at these settings."),
        ("numbers", "Even #1 alone is 40,001 chars at these settings."),
        ("matches", "Even one match is too large at these settings."),
    ],
)
def test_refusal_fit_range_single_unit_too_big(style, fit_line):
    with pytest.raises(TraceToolUsageError) as e:
        assemble(_units(40_001), None, None, RefusalContext(style, "advice"))
    assert str(e.value).splitlines()[1] == fit_line


def test_refusal_counts_header_footer_and_fit_footer():
    units = _units(19_000, 19_000, 1_000)
    with pytest.raises(TraceToolUsageError) as e:
        assemble(units, "h" * 1_000, "f" * 2_000, RefusalContext("matches", "advice"))
    assert "this would return 42,004 chars" in str(e.value)
    assert str(e.value).splitlines()[1] == "count=1 fits at these settings."

    fits_without_footer = _units(19_000, 19_000, 1_998)
    assert assemble(fits_without_footer, None, None, RefusalContext("matches", "a"))
    with pytest.raises(TraceToolUsageError) as e:
        assemble(
            [*fits_without_footer, Unit(4, "x" * 10)],
            None,
            None,
            RefusalContext("matches", "advice", fit_footer="f" * 10),
        )
    assert str(e.value).splitlines()[1] == "count=2 fits at these settings."


def test_read_refusal_single_message_too_big():
    view = _users("x" * 50_000)
    with pytest.raises(TraceToolUsageError) as e:
        read_messages(view, ReadArgs(max_chars=MAX_CHARS_MAX))
    assert "Even #1 alone is 40," in str(e.value)


@pytest.fixture(scope="module")
def synthetic_view():
    return build_view(golden_trace("synthetic"))


def _fit_range(message: str) -> tuple[int, int]:
    match = re.search(r"\(start=(\d+), end=(\d+)\)", message)
    assert match is not None
    return int(match.group(1)), int(match.group(2))


@pytest.mark.parametrize(
    "render, roles",
    [
        (
            lambda view, start, end, roles: preview_messages(
                view, PreviewArgs(start, end, roles)
            ),
            None,
        ),
        (
            lambda view, start, end, roles: read_messages(
                view, ReadArgs(None, start, end, roles)
            ),
            None,
        ),
        (
            lambda view, start, end, roles: read_messages(
                view, ReadArgs(None, start, end, roles, max_chars=5_000)
            ),
            ("tool",),
        ),
    ],
)
def test_refusal_fit_range_is_exact(synthetic_view, render, roles):
    with pytest.raises(TraceToolUsageError) as e:
        render(synthetic_view, 3, None, roles)
    start, end = _fit_range(str(e.value))
    assert len(render(synthetic_view, start, end, roles)) <= RESPONSE_CHARS
    next_selected = next(
        m.number
        for m in synthetic_view.messages[end:]
        if roles is None or m.role in roles
    )
    with pytest.raises(TraceToolUsageError):
        render(synthetic_view, start, next_selected, roles)


def test_refusal_fit_numbers_is_exact(synthetic_view):
    numbers = tuple(range(300, 900))
    with pytest.raises(TraceToolUsageError) as e:
        read_messages(synthetic_view, ReadArgs(numbers=numbers, roles=("tool",)))
    match = re.search(
        r"The first (\d+) of the requested messages fit \(through #(\d+)\)",
        str(e.value),
    )
    assert match is not None
    through = int(match.group(2))
    fitting = read_messages(
        synthetic_view,
        ReadArgs(numbers=tuple(n for n in numbers if n <= through), roles=("tool",)),
    )
    assert len(_block_headers(fitting)) == int(match.group(1))
