import json
import logging
import os
from enum import Enum
from typing import List, Literal

import uvicorn.logging
from kiln_ai.utils.logging import get_default_log_file_formatter, get_log_file_path


class PrettyPrintDictFormatter(uvicorn.logging.DefaultFormatter):
    """Custom formatter that displays props data from extra logging parameters.

    Usage:
    logger.info("Hello there", extra={"dict": {"key": "value"}})
    """

    def format(self, record: logging.LogRecord) -> str:
        # format with uvicorn's colored formatter
        formatted = super().format(record)

        # check if record has any keys
        dict_value = getattr(record, "dict", None)
        if dict_value:
            try:
                if isinstance(dict_value, dict):
                    dict_str = json.dumps(dict_value, ensure_ascii=False, indent=2)
                else:
                    dict_str = str(dict_value)
            except Exception as e:  # never fail logging due to serialization
                dict_str = f"<unserializable extra.dict: {e.__class__.__name__}>"
            formatted += f"\n{dict_str}"

        return formatted


class LogDestination(Enum):
    CONSOLE = "console"
    FILE = "file"
    ALL = "all"


class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


def validate_log_level(
    log_level: str,
) -> Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
    log_level_uppercase = log_level.upper()
    if log_level_uppercase not in LogLevel.__members__:
        raise ValueError(f"Invalid log level: {log_level}")
    return LogLevel(log_level_uppercase).value


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


def get_handlers() -> List[str]:
    destination = os.getenv("KILN_LOG_DESTINATION", "all")
    handlers = {
        LogDestination.FILE: ["logfile"],
        LogDestination.CONSOLE: ["logconsole"],
        LogDestination.ALL: ["logfile", "logconsole"],
    }
    return handlers[LogDestination(destination)]


def log_config(*, log_level: str, log_file_name: str):
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            # uvicorn expects a "default" formatter with colors
            "default": {
                "()": "uvicorn.logging.DefaultFormatter",
                "fmt": "%(levelprefix)s %(message)s",
                "use_colors": None,
            },
            # uvicorn expects an "access" formatter with colors for HTTP status codes
            "access": {
                "()": "uvicorn.logging.AccessFormatter",
                "fmt": '%(levelprefix)s %(client_addr)s - "%(request_line)s" %(status_code)s',
            },
            "logformatter": {
                "()": "app.desktop.log_config.PrettyPrintDictFormatter",
                "fmt": get_default_log_file_formatter(),
                "use_colors": None,
            },
            "console": {
                "()": "app.desktop.log_config.PrettyPrintDictFormatter",
                "fmt": "%(levelprefix)s %(message)s",
                "use_colors": None,
            },
        },
        "handlers": {
            "logfile": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": log_level,
                "formatter": "logformatter",
                "filename": get_log_file_path(log_file_name),
                "mode": "a",
                "maxBytes": get_max_file_bytes(),
                "backupCount": get_max_backup_count(),
            },
            "logconsole": {
                "class": "logging.StreamHandler",
                "level": log_level,
                "formatter": "console",
            },
            "default": {
                "class": "logging.StreamHandler",
                "level": log_level,
                "formatter": "default",
            },
            "access": {
                "class": "logging.StreamHandler",
                "level": log_level,
                "formatter": "access",
            },
        },
        "loggers": {
            "uvicorn": {
                "level": log_level,
                "handlers": ["default", "logfile"],
                "propagate": False,
            },
            "uvicorn.access": {
                "level": log_level,
                "handlers": ["access", "logfile"],
                "propagate": False,
            },
        },
        "root": {
            "level": log_level,
            "handlers": get_handlers(),
        },
    }
