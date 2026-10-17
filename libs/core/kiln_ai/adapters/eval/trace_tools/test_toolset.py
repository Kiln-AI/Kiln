from unittest.mock import Mock

import pytest

from kiln_ai.adapters.eval.trace_tools import (
    UnsupportedTraceToolsetVersion,
    judge_template_env,
    trace_toolset,
)
from kiln_ai.adapters.eval.trace_tools.v1 import TOOLSET_V1
from kiln_ai.utils.jinja_engine import JinjaExtractionError, _template_env

TRACE = [
    {"role": "user", "content": "Hello"},
    {"role": "assistant", "content": "Hi there"},
]
OVERVIEW_TEMPLATE = "{{ trace | trace_overview }}"


def test_trace_toolset_dispatch():
    assert trace_toolset(1) is TOOLSET_V1
    assert trace_toolset(1).version == 1


@pytest.mark.parametrize("version", [0, 2, 99])
def test_trace_toolset_unsupported_version(version):
    with pytest.raises(UnsupportedTraceToolsetVersion) as e:
        trace_toolset(version)
    assert e.value.version == version


def _spy_toolset() -> Mock:
    spy = Mock(wraps=TOOLSET_V1)
    spy.version = 1
    return spy


def _render(env, template: str = OVERVIEW_TEMPLATE, **namespace) -> str:
    return env.from_string(template).render(**namespace)


def test_judge_template_env_renders_toolset_overview():
    env = judge_template_env(TOOLSET_V1, TRACE, None)
    assert _render(env, trace=TRACE) == TOOLSET_V1.render_overview(
        TOOLSET_V1.build_view(TRACE)
    )


def test_judge_template_env_reuses_prebuilt_view():
    toolset = _spy_toolset()
    view = TOOLSET_V1.build_view(TRACE)
    env = judge_template_env(toolset, TRACE, view)
    _render(env, OVERVIEW_TEMPLATE + OVERVIEW_TEMPLATE, trace=TRACE)
    toolset.build_view.assert_not_called()
    assert toolset.render_overview.call_count == 2
    assert toolset.render_overview.call_args.args[0] is view


def test_judge_template_env_builds_view_once_when_none():
    toolset = _spy_toolset()
    env = judge_template_env(toolset, TRACE, None)
    _render(env, OVERVIEW_TEMPLATE + OVERVIEW_TEMPLATE, trace=TRACE)
    toolset.build_view.assert_called_once_with(TRACE)


def test_judge_template_env_never_builds_view_when_filter_unused():
    toolset = _spy_toolset()
    env = judge_template_env(toolset, TRACE, None)
    assert _render(env, "{{ trace | length }}", trace=TRACE) == "2"
    toolset.build_view.assert_not_called()


def test_judge_template_env_other_list_gets_own_view():
    toolset = _spy_toolset()
    prebuilt = TOOLSET_V1.build_view(TRACE)
    env = judge_template_env(toolset, TRACE, prebuilt)
    rendered = _render(env, "{{ trace[:1] | trace_overview }}", trace=TRACE)
    assert rendered.startswith("Trace: 1 message, 5 chars")
    toolset.build_view.assert_called_once_with(TRACE[:1])


@pytest.mark.parametrize(
    "value, message",
    [
        ("not a list", "expected a list of messages, got str"),
        (None, "expected a list of messages, got NoneType"),
        ([{"role": "user"}, "x"], "message 1 is str, not a dict"),
    ],
)
def test_judge_template_env_rejects_non_message_lists(value, message):
    env = judge_template_env(TOOLSET_V1, None, None)
    with pytest.raises(JinjaExtractionError, match=message):
        _render(env, trace=value)


def test_judge_template_env_keeps_base_env_and_other_filters():
    base_filters = dict(_template_env.filters)
    env = judge_template_env(TOOLSET_V1, TRACE, None)
    _render(env, trace=TRACE)
    assert dict(_template_env.filters) == base_filters
    assert (
        _template_env.filters.get("trace_overview") is not env.filters["trace_overview"]
    )
    assert _render(env, "{{ ('{\"a\": 1}' | fromjson).a }}") == "1"
    assert "user" in _render(env, "{{ trace | format_trace }}", trace=TRACE)


def test_judge_template_env_is_per_judgment():
    first = judge_template_env(TOOLSET_V1, TRACE, None)
    second = judge_template_env(TOOLSET_V1, TRACE, None)
    assert first.filters["trace_overview"] is not second.filters["trace_overview"]
