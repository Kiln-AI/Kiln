import time

import pytest

from kiln_ai.adapters.eval.trace_tools.v1.errors import TraceToolUsageError
from kiln_ai.adapters.eval.trace_tools.v1.limits import SEARCH_PATTERN_ELEMENTS_MAX
from kiln_ai.adapters.eval.trace_tools.v1.pattern_check import (
    check_regex_pattern,
    pattern_elements,
)

TOO_LARGE = r"^Pattern too large: it would compile to over 100,000 elements\."
UNSUPPORTED_FLAG = (
    r"^Verbose mode \(\?x\) and full case folding \(\?f\) aren't supported "
    r"in search patterns\."
)


@pytest.mark.parametrize(
    "pattern, elements",
    [
        ("abc", 3),
        ("a{5}", 5),
        ("a{2,}", 2),
        ("a{,3}", 3),
        ("a{2,7}", 7),
        ("a{0}", 1),
        ("a*b+c?", 3),
        ("(ab){3}", 9),
        ("(a{2}){3}", 9),
        ("(?:a{10}){10}x", 121),
        ("a{3}b{4}", 7),
        ("(a|bc){2}", 8),
        ("()", 2),
        ("(|)", 3),
        ("(){3}", 6),
        ("a|", 2),
        ("[abc]{4}", 4),
        ("[]{}]{4}", 4),
        (r"[^\]{]{4}", 4),
        (r"\d{4}", 4),
        (r"\p{L}{2}", 2),
        (r"\N{LATIN SMALL LETTER A}{3}", 3),
        (r"\{5}", 3),
        ("a{ 3}", 5),
        ("a{}", 3),
        ("a)b{2}", 4),
        ("((a){2}", 5),
    ],
)
def test_pattern_elements(pattern, elements):
    assert pattern_elements(pattern) == elements


@pytest.mark.parametrize(
    "pattern",
    [
        "a{100000000}",
        "(){100000000}",
        "(|){100000000}",
        "a{4294967294}",
        "a{100001,}",
        "a{0,100001}",
        "((((a{100}){100}){100}){100})",
        "(ab){33334}",
        "a{60000}b{60000}",
        r"\g{1000000}",
        "a{0000000000000001000000}",
        "x{" + "9" * 5_000 + "}",
        "[a-z]{100001}",
        "(?=a{100001})",
    ],
)
def test_large_counted_repeats_rejected_quickly(pattern):
    started = time.perf_counter()
    with pytest.raises(TraceToolUsageError, match=TOO_LARGE):
        check_regex_pattern(pattern)
    assert time.perf_counter() - started < 0.1


@pytest.mark.parametrize(
    "pattern",
    [
        r"\d{1,3}(\.\d{1,3}){3}",
        "[0-9a-f]{40} [0-9a-f]{40} [0-9a-f]{40}",
        r"FAILED tests/\S+::test_\w{1,200}",
        ".{0,2000}error.{0,2000}",
        "a" * SEARCH_PATTERN_ELEMENTS_MAX,
        f"a{{{SEARCH_PATTERN_ELEMENTS_MAX}}}",
        "(?i)abc",
        "(?-x:a b)",
        "(?i-f:a)",
        r"\(?x\)",
    ],
)
def test_ordinary_patterns_accepted(pattern):
    check_regex_pattern(pattern)


@pytest.mark.parametrize(
    "pattern",
    [
        "(?x)a {3}",
        "(?ix)a",
        "a(?x)b",
        "(?x:a)",
        "(?V1x)a",
        "(?ix-s:a)",
        "(?f)[a-z]",
        "(?if:a)",
    ],
)
def test_unsupported_inline_flags_rejected(pattern):
    with pytest.raises(TraceToolUsageError, match=UNSUPPORTED_FLAG):
        check_regex_pattern(pattern)


def test_verbose_flag_check_is_linear():
    started = time.perf_counter()
    check_regex_pattern("(?" + "x" * 50_000)
    assert time.perf_counter() - started < 0.5
