import pytest

from app.desktop.log_config import validate_log_level


class TestValidateLogLevel:
    """Tests for the validate_log_level function."""

    @pytest.mark.parametrize(
        "log_level,expected",
        [
            ("debug", "DEBUG"),
            ("info", "INFO"),
            ("warning", "WARNING"),
            ("error", "ERROR"),
            ("critical", "CRITICAL"),
            ("DEBUG", "DEBUG"),
            ("INFO", "INFO"),
            ("WARNING", "WARNING"),
            ("ERROR", "ERROR"),
            ("CRITICAL", "CRITICAL"),
            ("DebuG", "DEBUG"),
            ("InfO", "INFO"),
            ("WaRniNg", "WARNING"),
            ("ErroR", "ERROR"),
            ("CriTicaL", "CRITICAL"),
        ],
    )
    def test_valid_log_levels(self, log_level, expected):
        assert validate_log_level(log_level) == expected

    def test_invalid_log_level_raises_value_error(self):
        """Test that invalid log levels raise ValueError."""
        with pytest.raises(ValueError, match="Invalid log level: invalid"):
            validate_log_level("invalid")

        with pytest.raises(ValueError, match="Invalid log level: trace"):
            validate_log_level("trace")

        with pytest.raises(ValueError, match="Invalid log level: "):
            validate_log_level("")
