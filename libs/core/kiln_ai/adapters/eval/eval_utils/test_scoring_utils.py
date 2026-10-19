"""Tests for scoring_utils standalone functions."""

import math
from unittest.mock import Mock

import pytest
from kiln_ai.adapters.eval.eval_utils.scoring_utils import (
    build_g_eval_score,
    build_llm_as_judge_score,
    g_eval_single_metric,
    metric_offsets,
    rating_token_to_score,
    raw_output_from_logprobs,
    score_from_token_string,
    token_search_range,
)
from kiln_ai.adapters.run_output import RunOutput
from litellm.types.utils import ChatCompletionTokenLogprob, TopLogprob


class TestScoreFromTokenString:
    def test_direct_match(self):
        assert score_from_token_string("1") == 1.0
        assert score_from_token_string("5") == 5.0
        assert score_from_token_string("pass") == 1.0
        assert score_from_token_string("fail") == 0.0
        assert score_from_token_string("critical") == -1.0

    def test_uppercase(self):
        assert score_from_token_string("PASS") == 1.0
        assert score_from_token_string("FAIL") == 0.0
        assert score_from_token_string("Pass") == 1.0

    def test_whitespace(self):
        assert score_from_token_string(" 3 ") == 3.0
        assert score_from_token_string("  pass  ") == 1.0

    def test_quoted(self):
        assert score_from_token_string('"4"') == 4.0
        assert score_from_token_string('"pass"') == 1.0

    def test_float_string(self):
        assert score_from_token_string("3.0") == 3.0
        assert score_from_token_string("5.0") == 5.0

    def test_non_integer_float_returns_none(self):
        assert score_from_token_string("3.5") is None

    def test_invalid_returns_none(self):
        assert score_from_token_string("garbage") is None
        assert score_from_token_string("") is None
        assert score_from_token_string("6") is None
        assert score_from_token_string("abc") is None


class TestRawOutputFromLogprobs:
    def test_concatenates_tokens(self):
        logprobs = Mock()
        logprobs.content = [
            Mock(token='{"'),
            Mock(token="quality"),
            Mock(token='":'),
            Mock(token=" 3}"),
        ]
        run_output = RunOutput(
            output={"quality": "3"},
            intermediate_outputs=None,
            output_logprobs=logprobs,
        )
        result = raw_output_from_logprobs(run_output)
        assert result == '{"quality": 3}'

    def test_no_logprobs_raises(self):
        run_output = RunOutput(
            output={"quality": "3"},
            intermediate_outputs=None,
            output_logprobs=None,
        )
        with pytest.raises(RuntimeError, match="No logprobs"):
            raw_output_from_logprobs(run_output)

    def test_none_content_raises(self):
        logprobs = Mock()
        logprobs.content = None
        run_output = RunOutput(
            output={"quality": "3"},
            intermediate_outputs=None,
            output_logprobs=logprobs,
        )
        with pytest.raises(RuntimeError, match="No logprobs"):
            raw_output_from_logprobs(run_output)


class TestMetricOffsets:
    def test_single_metric(self):
        raw = '{"quality": 3}'
        result = metric_offsets(raw, ["quality"])
        assert result == {"quality": 1}

    def test_multiple_metrics(self):
        raw = '{"quality": 3, "relevance": 5}'
        result = metric_offsets(raw, ["quality", "relevance"])
        assert result["quality"] == 1
        assert "relevance" in result

    def test_duplicate_metric_raises(self):
        raw = '{"quality": 3, "quality": 5}'
        with pytest.raises(ValueError, match="exactly once"):
            metric_offsets(raw, ["quality"])

    def test_missing_metric_raises(self):
        raw = '{"quality": 3}'
        with pytest.raises(ValueError, match="exactly once"):
            metric_offsets(raw, ["missing_metric"])


class TestTokenSearchRange:
    def test_single_metric_range(self):
        raw = '{"quality": 3}'
        offsets = {"quality": 1}
        start, end = token_search_range(raw, "quality", offsets)
        assert start == 1 + len("quality")
        assert end == len(raw)

    def test_multiple_metrics_bounded(self):
        raw = '{"quality": 3, "relevance": 5}'
        offs = metric_offsets(raw, ["quality", "relevance"])
        start, end = token_search_range(raw, "quality", offs)
        assert start == offs["quality"] + len("quality")
        assert end == offs["relevance"]


class TestRatingTokenToScore:
    def _make_logprob(
        self,
        token: str,
        logprob: float,
        top_logprobs: list[TopLogprob] | None = None,
    ) -> ChatCompletionTokenLogprob:
        return ChatCompletionTokenLogprob(
            token=token,
            logprob=logprob,
            bytes=None,
            top_logprobs=top_logprobs or [],
        )

    def test_single_token_no_top_logprobs(self):
        lp = self._make_logprob("3", -0.5)
        score = rating_token_to_score(lp)
        assert score is not None
        assert score == pytest.approx(3.0)

    def test_non_scoring_token_returns_none(self):
        lp = self._make_logprob("{", -0.1)
        assert rating_token_to_score(lp) is None

    def test_weighted_average_with_top_logprobs(self):
        top = [
            TopLogprob(token="3", logprob=math.log(0.6), bytes=None),
            TopLogprob(token="4", logprob=math.log(0.3), bytes=None),
            TopLogprob(token="5", logprob=math.log(0.1), bytes=None),
        ]
        lp = self._make_logprob("3", math.log(0.6), top_logprobs=top)
        score = rating_token_to_score(lp)
        assert score is not None
        expected = (3.0 * 0.6 + 4.0 * 0.3 + 5.0 * 0.1) / (0.6 + 0.3 + 0.1)
        assert score == pytest.approx(expected)

    def test_primary_not_in_top_logprobs_added(self):
        top = [
            TopLogprob(token="4", logprob=math.log(0.5), bytes=None),
        ]
        lp = self._make_logprob("3", math.log(0.3), top_logprobs=top)
        score = rating_token_to_score(lp)
        assert score is not None
        expected = (4.0 * 0.5 + 3.0 * 0.3) / (0.5 + 0.3)
        assert score == pytest.approx(expected)

    def test_primary_not_in_top_logprobs_sentinel(self):
        top = [
            TopLogprob(token="4", logprob=math.log(0.5), bytes=None),
        ]
        lp = self._make_logprob("3", -9999.0, top_logprobs=top)
        score = rating_token_to_score(lp)
        assert score is not None
        expected = (4.0 * 0.5 + 3.0 * 1.0) / (0.5 + 1.0)
        assert score == pytest.approx(expected)


class TestGEvalSingleMetric:
    def _make_run_output(self, tokens, logprobs_list=None):
        content = []
        for i, t in enumerate(tokens):
            lp_val = logprobs_list[i] if logprobs_list else -0.1
            content.append(
                ChatCompletionTokenLogprob(
                    token=t,
                    logprob=lp_val,
                    bytes=None,
                    top_logprobs=[],
                )
            )
        logprobs = Mock()
        logprobs.content = content
        return RunOutput(
            output={"quality": "3"},
            intermediate_outputs=None,
            output_logprobs=logprobs,
        )

    def test_finds_score_token(self):
        tokens = ['{"', '"', "quality", '"', ":", " ", "3", "}"]
        run_output = self._make_run_output(tokens)
        raw = "".join(tokens)
        offs = metric_offsets(raw, ["quality"])
        score = g_eval_single_metric(run_output, "quality", offs, raw)
        assert score is not None
        assert score == pytest.approx(3.0)

    def test_no_scoring_token_returns_none(self):
        tokens = ['{"', '"', "quality", '"', ":", " ", '"', "abc", '"', "}"]
        run_output = self._make_run_output(tokens)
        raw = "".join(tokens)
        offs = metric_offsets(raw, ["quality"])
        score = g_eval_single_metric(run_output, "quality", offs, raw)
        assert score is None

    def test_no_logprobs_raises(self):
        run_output = RunOutput(
            output={"quality": "3"},
            intermediate_outputs=None,
            output_logprobs=None,
        )
        with pytest.raises(RuntimeError, match="No logprobs"):
            g_eval_single_metric(run_output, "quality", {"quality": 0}, "")


class TestBuildLlmAsJudgeScore:
    def test_basic_dict_output(self):
        run_output = RunOutput(
            output={"quality": "4", "relevance": "pass"},
            intermediate_outputs=None,
        )
        scores = build_llm_as_judge_score(run_output, score_from_token_string)
        assert scores == {"quality": 4.0, "relevance": 1.0}

    def test_non_dict_raises(self):
        run_output = RunOutput(
            output="just a string",
            intermediate_outputs=None,
        )
        with pytest.raises(ValueError, match="must be a dictionary"):
            build_llm_as_judge_score(run_output, score_from_token_string)

    def test_invalid_score_raises(self):
        run_output = RunOutput(
            output={"quality": "garbage"},
            intermediate_outputs=None,
        )
        with pytest.raises(ValueError, match="No score found"):
            build_llm_as_judge_score(run_output, score_from_token_string)

    def test_custom_score_fn(self):
        def custom_fn(token: str) -> float | None:
            return 99.0 if token == "special" else None

        run_output = RunOutput(
            output={"metric": "special"},
            intermediate_outputs=None,
        )
        scores = build_llm_as_judge_score(run_output, custom_fn)
        assert scores == {"metric": 99.0}

    def test_non_mapping_float_raises(self):
        run_output = RunOutput(
            output={"quality": "3.7"},
            intermediate_outputs=None,
        )
        with pytest.raises(ValueError, match="No score found"):
            build_llm_as_judge_score(run_output, score_from_token_string)

    def test_raw_int_value_maps_via_token_string(self):
        run_output = RunOutput(
            output={"quality": 4},
            intermediate_outputs=None,
        )
        scores = build_llm_as_judge_score(run_output, score_from_token_string)
        assert scores == {"quality": 4.0}

    def test_raw_float_non_integer_raises(self):
        run_output = RunOutput(
            output={"quality": 3.7},
            intermediate_outputs=None,
        )
        with pytest.raises(ValueError, match="No score found"):
            build_llm_as_judge_score(run_output, score_from_token_string)


class TestBuildGEvalScore:
    def test_delegates_to_functions(self):
        run_output = RunOutput(
            output={"quality": "3", "relevance": "4"},
            intermediate_outputs=None,
        )

        mock_raw = Mock(return_value='{"quality": 3, "relevance": 4}')
        mock_offsets = Mock(return_value={"quality": 1, "relevance": 16})
        mock_single = Mock(side_effect=[3.5, 4.2])

        scores = build_g_eval_score(run_output, mock_raw, mock_offsets, mock_single)
        assert scores == {"quality": 3.5, "relevance": 4.2}
        mock_raw.assert_called_once_with(run_output)
        mock_offsets.assert_called_once()
        assert mock_single.call_count == 2

    def test_non_dict_raises(self):
        run_output = RunOutput(
            output="not a dict",
            intermediate_outputs=None,
        )
        with pytest.raises(ValueError, match="must be a dictionary"):
            build_g_eval_score(run_output, Mock(), Mock(), Mock())

    def test_none_score_raises(self):
        run_output = RunOutput(
            output={"quality": "3"},
            intermediate_outputs=None,
        )
        mock_raw = Mock(return_value='{"quality": 3}')
        mock_offsets = Mock(return_value={"quality": 1})
        mock_single = Mock(return_value=None)

        with pytest.raises(ValueError, match="No score found"):
            build_g_eval_score(run_output, mock_raw, mock_offsets, mock_single)
