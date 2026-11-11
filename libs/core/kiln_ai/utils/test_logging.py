import logging
from unittest.mock import MagicMock, patch

import pytest

from kiln_ai.utils.logging import CustomLiteLLMLogger


def _kwargs():
    return {
        "litellm_params": {"api_base": "https://example.invalid/v1"},
        "additional_args": {"headers": {}, "complete_input_dict": {"model": "m"}},
    }


@pytest.fixture
def model_calls_logger():
    logger = logging.getLogger("test_model_calls")
    previous_level = logger.level
    yield logger
    logger.setLevel(previous_level)


def test_log_pre_api_call_logs_at_info(model_calls_logger, caplog):
    model_calls_logger.setLevel(logging.INFO)

    with caplog.at_level(logging.INFO, logger=model_calls_logger.name):
        CustomLiteLLMLogger(model_calls_logger).log_pre_api_call(
            "m", [{"role": "user", "content": "hi"}], _kwargs()
        )

    messages = [record.getMessage() for record in caplog.records]
    assert any(m.startswith("Formatted Input Data (API):") for m in messages)
    assert any(m.startswith("Messages:") for m in messages)


def test_log_pre_api_call_skips_formatting_when_info_disabled(model_calls_logger):
    model_calls_logger.setLevel(logging.WARNING)
    kwargs = MagicMock()

    with patch("kiln_ai.utils.logging.Logging") as litellm_logging:
        CustomLiteLLMLogger(model_calls_logger).log_pre_api_call(
            "m", [{"role": "user", "content": "hi"}], kwargs
        )

    # The request is never read, so nothing is formatted.
    kwargs.get.assert_not_called()
    litellm_logging.assert_not_called()
