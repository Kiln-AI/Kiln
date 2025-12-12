import logging
import time
from unittest.mock import patch

import pytest

import kiln_ai.utils.timing_logger as timing_logger
from kiln_ai.utils.timing_logger import TimingLogger, time_operation


@pytest.fixture(autouse=True)
def reset_show_timing():
    old_show_timing = timing_logger._show_timing
    yield
    timing_logger._show_timing = old_show_timing


class TestTimingLogger:
    """Test cases for TimingLogger class."""

    def test_timing_logger_basic_usage(self, caplog):
        """Test basic timing logger functionality."""
        timing_logger._show_timing = True
        with caplog.at_level(logging.WARNING):
            with TimingLogger("test", "test_operation"):
                time.sleep(0.1)

        assert len(caplog.records) == 1
        assert "timing_logger [test][test_operation]" in caplog.records[0].message
        assert caplog.records[0].levelno == logging.WARNING

    def test_timing_logger_logs_at_warning_level(self, caplog):
        """Test that timing logger uses WARNING level when enabled."""
        timing_logger._show_timing = True
        with caplog.at_level(logging.WARNING):
            with TimingLogger("test", "level_test"):
                time.sleep(0.05)

        assert len(caplog.records) == 1
        assert caplog.records[0].levelname == "WARNING"
        assert caplog.records[0].levelno == logging.WARNING

    def test_timing_logger_not_logged_when_disabled(self, caplog):
        """Test that timing messages don't appear when timing is disabled."""
        timing_logger._show_timing = False
        with caplog.at_level(logging.WARNING):
            with TimingLogger("test", "filtered_test"):
                time.sleep(0.05)

        assert len(caplog.records) == 0

    @patch("kiln_ai.utils.timing_logger.time.time")
    def test_timing_calculation(self, mock_time, caplog):
        """Test that timing calculation is accurate."""
        timing_logger._show_timing = True
        # Mock time.time() to return predictable values
        # Need 3 values: __enter__, __exit__, and logging internal call
        mock_time.side_effect = [1000.0, 1002.5, 1003.0]  # 2.5 second difference

        with caplog.at_level(logging.WARNING):
            with TimingLogger("test", "precise_test"):
                pass

        assert len(caplog.records) == 1
        assert "timing_logger [test][precise_test][2.50s]" in caplog.records[0].message

    def test_timestamp_format(self):
        """Test that timestamp format is ISO format."""
        timing_logger = TimingLogger("test", "timestamp_test")
        timestamp = timing_logger.timestamp()

        # Should be in ISO format (contains T and colons)
        assert "T" in timestamp
        assert ":" in timestamp


class TestTimeOperationContextManager:
    """Test cases for time_operation context manager function."""

    def test_time_operation_basic(self, caplog):
        """Test basic time_operation context manager."""
        timing_logger._show_timing = True
        with caplog.at_level(logging.WARNING):
            with time_operation("test", "context_test"):
                time.sleep(0.1)

        assert len(caplog.records) == 1
        assert "timing_logger [test][context_test]" in caplog.records[0].message

    def test_time_operation_exception_handling(self, caplog):
        """Test that timing is still logged even if an exception occurs."""
        timing_logger._show_timing = True
        with caplog.at_level(logging.WARNING):
            with pytest.raises(ValueError):
                with time_operation("test", "exception_test"):
                    raise ValueError("Test exception")

        assert len(caplog.records) == 1
        assert "timing_logger [test][exception_test]" in caplog.records[0].message


class TestShowTimingControl:
    """Test cases for _show_timing flag control of timing logging."""

    def test_timing_disabled_by_default(self, caplog):
        """Test that timing is disabled when _show_timing is False."""
        timing_logger._show_timing = False
        with caplog.at_level(logging.WARNING):
            with TimingLogger("test", "default_test"):
                time.sleep(0.05)

        assert len(caplog.records) == 0

    def test_timing_disabled_when_false(self, caplog):
        """Test that timing is disabled when _show_timing is False."""
        timing_logger._show_timing = False
        with caplog.at_level(logging.WARNING):
            with TimingLogger("test", "false_test"):
                time.sleep(0.05)

        assert len(caplog.records) == 0

    def test_timing_enabled_when_true(self, caplog):
        """Test that timing is enabled when _show_timing is True."""
        timing_logger._show_timing = True
        with caplog.at_level(logging.WARNING):
            with TimingLogger("test", "true_test"):
                time.sleep(0.05)

        assert len(caplog.records) == 1
        assert "timing_logger [test][true_test]" in caplog.records[0].message
