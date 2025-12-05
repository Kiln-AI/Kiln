import logging
import os
import time
from unittest.mock import patch

import pytest

from kiln_ai.utils.timing_logger import TimingLogger, time_operation


class TestTimingLogger:
    """Test cases for TimingLogger class."""

    def test_timing_logger_basic_usage(self, caplog):
        """Test basic timing logger functionality."""
        with patch.dict(os.environ, {"KILN_SHOW_TIMING": "true"}):
            with caplog.at_level(logging.WARNING):
                with TimingLogger("test", "test_operation"):
                    time.sleep(0.1)

        assert len(caplog.records) == 1
        assert "timing_logger [test][test_operation]" in caplog.records[0].message
        assert caplog.records[0].levelno == logging.WARNING

    def test_timing_logger_logs_at_warning_level(self, caplog):
        """Test that timing logger uses WARNING level when enabled."""
        with patch.dict(os.environ, {"KILN_SHOW_TIMING": "true"}):
            with caplog.at_level(logging.WARNING):
                with TimingLogger("test", "level_test"):
                    time.sleep(0.05)

        assert len(caplog.records) == 1
        assert caplog.records[0].levelname == "WARNING"
        assert caplog.records[0].levelno == logging.WARNING

    def test_timing_logger_not_logged_when_disabled(self, caplog):
        """Test that timing messages don't appear when KILN_SHOW_TIMING is false."""
        with patch.dict(os.environ, {"KILN_SHOW_TIMING": "false"}):
            with caplog.at_level(logging.WARNING):
                with TimingLogger("test", "filtered_test"):
                    time.sleep(0.05)

        assert len(caplog.records) == 0

    @patch("kiln_ai.utils.timing_logger.time.time")
    def test_timing_calculation(self, mock_time, caplog):
        """Test that timing calculation is accurate."""
        # Mock time.time() to return predictable values
        # Need 3 values: __enter__, __exit__, and logging internal call
        mock_time.side_effect = [1000.0, 1002.5, 1003.0]  # 2.5 second difference

        with patch.dict(os.environ, {"KILN_SHOW_TIMING": "true"}):
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
        with patch.dict(os.environ, {"KILN_SHOW_TIMING": "true"}):
            with caplog.at_level(logging.WARNING):
                with time_operation("test", "context_test"):
                    time.sleep(0.1)

        assert len(caplog.records) == 1
        assert "timing_logger [test][context_test]" in caplog.records[0].message

    def test_time_operation_exception_handling(self, caplog):
        """Test that timing is still logged even if an exception occurs."""
        with patch.dict(os.environ, {"KILN_SHOW_TIMING": "true"}):
            with caplog.at_level(logging.WARNING):
                with pytest.raises(ValueError):
                    with time_operation("test", "exception_test"):
                        raise ValueError("Test exception")

        assert len(caplog.records) == 1
        assert "timing_logger [test][exception_test]" in caplog.records[0].message


class TestEnvironmentVariableControl:
    """Test cases for environment variable control of timing logging."""

    def test_timing_disabled_by_default(self, caplog):
        """Test that timing is disabled when KILN_SHOW_TIMING is not set."""
        # Ensure the environment variable is not set
        with patch.dict(os.environ, {}, clear=True):
            with caplog.at_level(logging.WARNING):
                with TimingLogger("test", "default_test"):
                    time.sleep(0.05)

        assert len(caplog.records) == 0

    def test_timing_disabled_when_false(self, caplog):
        """Test that timing is disabled when KILN_SHOW_TIMING is 'false'."""
        with patch.dict(os.environ, {"KILN_SHOW_TIMING": "false"}):
            with caplog.at_level(logging.WARNING):
                with TimingLogger("test", "false_test"):
                    time.sleep(0.05)

        assert len(caplog.records) == 0

    def test_timing_enabled_when_true(self, caplog):
        """Test that timing is enabled when KILN_SHOW_TIMING is 'true'."""
        with patch.dict(os.environ, {"KILN_SHOW_TIMING": "true"}):
            with caplog.at_level(logging.WARNING):
                with TimingLogger("test", "true_test"):
                    time.sleep(0.05)

        assert len(caplog.records) == 1
        assert "timing_logger [test][true_test]" in caplog.records[0].message
