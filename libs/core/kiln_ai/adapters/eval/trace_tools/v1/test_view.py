import json

import pytest

from kiln_ai.adapters.eval.trace_tools.v1.view import (
    UNKNOWN_TOOL,
    MessageView,
    build_view,
)


def _call(call_id, name, arguments="{}"):
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": arguments},
    }


def _only(message) -> MessageView:
    return build_view([message]).message(1)


@pytest.mark.parametrize(
    "stored_role, view_role",
    [
        ("system", "system"),
        ("developer", "developer"),
        ("user", "user"),
        ("assistant", "assistant"),
        ("tool", "tool"),
        ("function", "tool"),
        ("critic", "critic"),
        (None, "unknown"),
        (7, "unknown"),
    ],
)
def test_view_role_mapping(stored_role, view_role):
    message = {"content": "x"} if stored_role is None else {"role": stored_role}
    assert _only(message).role == view_role


def test_view_numbers_from_one_including_system(coding_view):
    assert [m.number for m in coding_view.messages] == list(range(1, 17))
    assert coding_view.count == 16
    assert coding_view.message(1).role == "system"
    assert coding_view.message(16).role == "assistant"


def test_view_content_list_parts():
    content = [
        {"type": "text", "text": "first"},
        {"type": "image_url", "image_url": {"url": "x"}},
        {"type": "input_audio", "input_audio": {}},
        {"type": "file", "file": {}},
        {"type": "refusal", "refusal": "no"},
        {"type": "video"},
        {"type": "text"},
        "stray",
        {"text": "no type"},
        {"type": 3},
        {"type": "text", "text": "last"},
    ]
    assert _only({"role": "user", "content": content}).content == (
        "first\n[image]\n[audio]\n[file]\n[refusal] no\n[video]\n[text]\nlast"
    )


@pytest.mark.parametrize("content", [None, 12, {"type": "text", "text": "x"}])
def test_view_non_text_content_is_empty(content):
    assert _only({"role": "user", "content": content}).content == ""


@pytest.mark.parametrize(
    "role, content, expected",
    [
        ("tool", '{"output": "the answer"}', "the answer"),
        (
            "tool",
            '{"output": "the answer", "exit_code": 1}',
            '{"output": "the answer", "exit_code": 1}',
        ),
        ("tool", '  \n{"output": ""}', ""),
        ("function", '{"output": "legacy"}', "legacy"),
        ("tool", '{"output": 5}', '{"output": 5}'),
        ("tool", '["output"]', '["output"]'),
        ("tool", "{not json", "{not json"),
        ("tool", "plain text", "plain text"),
        ("user", '{"output": "kept"}', '{"output": "kept"}'),
        ("tool", '{"output": "smile \\ud83d\\ude00"}', "smile \U0001f600"),
    ],
)
def test_view_kiln_task_tool_output_extracted(role, content, expected):
    assert _only({"role": role, "content": content}).content == expected


@pytest.mark.parametrize(
    "content",
    ['{"output":  "smile \\ud83d done"}', '{"output": "\\ude00 then \\ud83d"}'],
)
def test_view_task_tool_output_with_lone_surrogate_kept_as_stored(content):
    message = _only({"role": "tool", "content": content})
    message.content.encode("utf-8")
    assert message.content == content


def test_view_kiln_task_tool_output_from_list_content():
    message = {"role": "tool", "content": [{"type": "text", "text": '{"output": "x"}'}]}
    assert _only(message).content == "x"


@pytest.mark.parametrize(
    "content, calls, expected_content",
    [
        (None, [_call("a", "task_response", '{"x":  1}')], '{"x": 1}'),
        (
            "Here it is.",
            [
                _call("a", "task_response", '{"x": 1}'),
                _call("b", "task_response", '{"x": 2}'),
            ],
            'Here it is.\n\n{"x": 2}',
        ),
    ],
)
def test_view_task_response_is_content_not_call(content, calls, expected_content):
    message = _only({"role": "assistant", "content": content, "tool_calls": calls})
    assert message.content == expected_content
    assert message.tool_calls == ()
    assert message.tool_calls_text == ""


def test_view_structured_answer_and_refusal_only_on_assistant_messages():
    message = _only(
        {
            "role": "user",
            "content": "Hi",
            "refusal": "No.",
            "tool_calls": [_call("a", "task_response", '{"x": 1}')],
        }
    )
    assert message.content == "Hi"
    assert message.tool_calls == ()


def test_view_assistant_refusal_appended():
    assert _only(
        {"role": "assistant", "content": "Hmm.", "refusal": "No."}
    ).content == ("Hmm.\n\n[refusal] No.")
    assert _only({"role": "assistant", "content": None, "refusal": ""}).content == ""


@pytest.mark.parametrize(
    "function, expected",
    [
        ({"name": "f", "arguments": '{"b":  1,\n "a": "é"}'}, 'f {"b": 1, "a": "é"}'),
        ({"name": "f", "arguments": "{not json"}, "f {not json"),
        (
            {"name": "f", "arguments": '{"a": "\\ud83d\\ude00"}'},
            'f {"a": "\U0001f600"}',
        ),
        ({"name": "f", "arguments": {"a": [1, 2]}}, 'f {"a": [1, 2]}'),
        ({"name": "f", "arguments": None}, "f null"),
        ({"name": "f"}, "f "),
        ({"arguments": "{}"}, "unknown {}"),
        ({"name": "", "arguments": "{}"}, "unknown {}"),
    ],
)
def test_view_tool_args_canonicalized(function, expected):
    message = {"role": "assistant", "tool_calls": [{"id": "a", "function": function}]}
    assert _only(message).tool_calls_text == expected


def test_view_unserializable_arguments_fall_back_to_str():
    arguments = {(1, 2): "tuple key"}
    message = {
        "role": "assistant",
        "tool_calls": [{"id": "a", "function": {"name": "f", "arguments": arguments}}],
    }
    assert _only(message).tool_calls_text == f"f {arguments}"


@pytest.mark.parametrize(
    "arguments", ['{"text":  "smile \\ud83d done"}', '["\\ude00 then \\ud83d"]']
)
def test_view_tool_args_with_lone_surrogate_kept_as_stored(arguments):
    message = _only(
        {
            "role": "assistant",
            "tool_calls": [
                _call("a", "f", arguments),
                _call("b", "task_response", arguments),
            ],
            "function_call": {"name": "g", "arguments": arguments},
        }
    )
    message.tool_calls_text.encode("utf-8")
    message.content.encode("utf-8")
    assert [call.arguments for call in message.tool_calls] == [arguments, arguments]
    assert message.content == arguments


def test_view_tool_calls_text_one_line_per_call():
    message = _only(
        {
            "role": "assistant",
            "tool_calls": [_call("a", "read", '{"p": 1}'), _call("b", "grep", "{}")],
        }
    )
    assert message.tool_calls_text == 'read {"p": 1}\ngrep {}'
    assert [call.name for call in message.tool_calls] == ["read", "grep"]


def test_view_tool_name_resolution():
    view = build_view(
        [
            {
                "role": "assistant",
                "tool_calls": [
                    _call("a", "read"),
                    _call("b", "grep"),
                    _call("c", "never_answered"),
                ],
            },
            {"role": "tool", "tool_call_id": "a", "content": "first"},
            {"role": "tool", "tool_call_id": "a", "content": "second"},
            {"role": "tool", "tool_call_id": "zzz", "content": "orphan"},
            {"role": "tool", "content": "no id"},
            {"role": "function", "name": "legacy", "content": "legacy result"},
            {
                "role": "tool",
                "tool_call_id": "b",
                "content": "grep result",
                "is_error": True,
            },
        ]
    )
    assert [view.message(n).tool_name for n in range(2, 8)] == [
        "read",
        UNKNOWN_TOOL,
        UNKNOWN_TOOL,
        UNKNOWN_TOOL,
        "legacy",
        "grep",
    ]
    assert [call.result_number for call in view.message(1).tool_calls] == [2, 7, None]
    assert view.message(1).tool_name is None
    assert view.message(7).is_error


def _assistant(*calls):
    return {"role": "assistant", "tool_calls": list(calls)}


def _result(call_id):
    return {"role": "tool", "tool_call_id": call_id, "content": "x"}


@pytest.mark.parametrize(
    "trace, tool_names, result_numbers",
    [
        pytest.param(
            [
                _assistant(_call("a", "read"), _call("b", "grep")),
                _result("b"),
                _result("a"),
            ],
            [None, "grep", "read"],
            [[3, 2], [], []],
            id="unique_ids",
        ),
        pytest.param(
            [
                _assistant(_call("call_0", "read")),
                _result("call_0"),
                _assistant(_call("call_0", "grep")),
                _result("call_0"),
            ],
            [None, "read", None, "grep"],
            [[2], [], [4], []],
            id="id_reused_across_turns",
        ),
        pytest.param(
            [_result("a"), _assistant(_call("a", "read")), _result("zzz")],
            [UNKNOWN_TOOL, None, UNKNOWN_TOOL],
            [[], [None], []],
            id="result_with_no_earlier_call",
        ),
        pytest.param(
            [
                _assistant(_call("a", "read"), _call("a", "grep")),
                _result("a"),
                _result("a"),
            ],
            [None, "read", "grep"],
            [[2, 3], [], []],
            id="parallel_calls_share_an_id",
        ),
        pytest.param(
            [
                _assistant(_call("a", "read")),
                _assistant(_call("a", "grep")),
                _result("a"),
            ],
            [None, None, "grep"],
            [[None], [3], []],
            id="latest_unanswered_call_wins",
        ),
    ],
)
def test_view_links_each_result_to_the_call_it_answers(
    trace, tool_names, result_numbers
):
    view = build_view(trace)
    assert [m.tool_name for m in view.messages] == tool_names
    assert [[c.result_number for c in m.tool_calls] for m in view.messages] == (
        result_numbers
    )


@pytest.mark.parametrize("is_error", ["yes", 1, None])
def test_view_is_error_must_be_true(is_error):
    assert not _only({"role": "tool", "content": "x", "is_error": is_error}).is_error


def test_view_is_error_only_on_tool_results():
    assert not _only({"role": "assistant", "content": "x", "is_error": True}).is_error


def test_view_legacy_function_call_counts_as_call():
    message = _only(
        {
            "role": "assistant",
            "tool_calls": [_call("a", "first")],
            "function_call": {"name": "legacy", "arguments": '{"x":1}'},
        }
    )
    assert message.tool_calls_text == 'first {}\nlegacy {"x": 1}'
    assert message.tool_calls[1].call_id is None


@pytest.mark.parametrize(
    "message",
    [
        "not a dict",
        None,
        42,
        {},
        {"role": "assistant", "tool_calls": "nope"},
        {"role": "assistant", "tool_calls": [None, "x", {"function": "x"}, {"id": 5}]},
        {"role": "assistant", "function_call": "nope", "refusal": 3},
        {"role": "tool", "tool_call_id": ["a"], "content": {"output": "x"}},
        {"role": "assistant", "reasoning_content": 5, "content": [None, 3]},
        {"role": "tool", "content": '{"a":' * 100_000},
        {"role": "assistant", "tool_calls": [_call("a", "f", "[" * 100_000)]},
    ],
)
def test_view_loose_dicts_never_raise(message):
    view = build_view([message, {"role": "user", "content": "after"}])
    assert view.count == 2
    assert view.message(2).content == "after"


def test_view_sizes_and_part_text():
    message = _only(
        {
            "role": "assistant",
            "content": "abc",
            "reasoning_content": "de",
            "tool_calls": [_call("a", "f", json.dumps({"k": 1}, ensure_ascii=False))],
        }
    )
    assert message.total_chars == 3 + 2 + len('f {"k": 1}')
    assert message.non_empty_parts() == ("content", "reasoning", "tool_calls")
    assert [message.part(p) for p in ("content", "reasoning", "tool_calls")] == [
        "abc",
        "de",
        'f {"k": 1}',
    ]
    assert build_view([{"role": "user", "content": "x"}]).part_text(1, "content") == "x"
