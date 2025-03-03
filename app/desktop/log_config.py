import os
from enum import Enum
from typing import List

from kiln_ai.utils.config import Config


class LogDestination(Enum):
    CONSOLE = "console"
    FILE = "file"
    ALL = "all"


def get_log_level() -> str:
    return os.getenv("KILN_LOG_LEVEL", "WARNING")


def get_log_file_path() -> str:
    """Get the path to the log file, using environment override if specified.

    Returns:
        str: The path to the log file
    """
    log_path_default = os.path.join(Config.settings_dir(), "logs", "kiln_desktop.log")
    log_path = os.getenv("KILN_LOG_FILE", log_path_default)

    # Ensure the log directory exists
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    return log_path


def get_max_file_bytes() -> int:
    """
    The maximum number of bytes to write to the log file.
    When the file reaches this size, it will be rotated.
    """
    default_max_bytes = 20971520  # 20MB
    return int(os.getenv("KILN_LOG_MAX_BYTES", default_max_bytes))


def get_max_backup_count() -> int:
    """
    The number of backup files to keep in the log directory.
    Past that, the oldest files are deleted.
    """
    default_backup_count = 3
    return int(os.getenv("KILN_LOG_BACKUP_COUNT", default_backup_count))


def get_default_formatter() -> str:
    return "%(asctime)s.%(msecs)03d - %(levelname)s - %(name)s - %(message)s"


def get_handlers() -> List[str]:
    destination = os.getenv("KILN_LOG_DESTINATION", "all")
    handlers = {
        LogDestination.FILE: ["logfile"],
        LogDestination.CONSOLE: ["logconsole"],
        LogDestination.ALL: ["logfile", "logconsole"],
    }
    return handlers[LogDestination(destination)]


def log_config():
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            # uvicorn expects a "default" formatter
            "default": {
                "format": get_default_formatter(),
            },
            # uvicorn expects an "access" formatter
            "access": {
                "format": get_default_formatter(),
            },
            "logformatter": {
                "format": get_default_formatter(),
            },
            "console": {
                "format": "%(levelname)s: %(message)s",
            },
        },
        "handlers": {
            "logfile": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": get_log_level(),
                "formatter": "logformatter",
                "filename": get_log_file_path(),
                "mode": "a",
                "maxBytes": get_max_file_bytes(),
                "backupCount": get_max_backup_count(),
            },
            "logconsole": {
                "class": "logging.StreamHandler",
                "level": get_log_level(),
                "formatter": "console",
            },
        },
        "root": {"level": get_log_level(), "handlers": get_handlers()},
    }
