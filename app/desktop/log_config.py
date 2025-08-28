import json
import os
from enum import Enum
from typing import List

import uvicorn.logging
from kiln_ai.utils.logging import get_default_formatter, get_log_file_path


class KilnConsoleFormatter(uvicorn.logging.DefaultFormatter):
    """Custom formatter that displays props data from extra logging parameters."""

    def format(self, record):
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
                formatted += f"\n{dict_str}"
            except Exception:
                pass

        return formatted


class LogDestination(Enum):
    CONSOLE = "console"
    FILE = "file"
    ALL = "all"


def get_log_level() -> str:
    return os.getenv("KILN_LOG_LEVEL", "WARNING")


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


def log_config():
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
                "()": "app.desktop.log_config.KilnConsoleFormatter",
                "fmt": get_default_formatter(),
                "use_colors": None,
            },
            "console": {
                "()": "app.desktop.log_config.KilnConsoleFormatter",
                "fmt": "%(levelprefix)s %(message)s",
                "use_colors": None,
            },
        },
        "handlers": {
            "logfile": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": get_log_level(),
                "formatter": "logformatter",
                "filename": get_log_file_path("kiln_desktop.log"),
                "mode": "a",
                "maxBytes": get_max_file_bytes(),
                "backupCount": get_max_backup_count(),
            },
            "logconsole": {
                "class": "logging.StreamHandler",
                "level": get_log_level(),
                "formatter": "console",
            },
            "default": {
                "class": "logging.StreamHandler",
                "level": "INFO",
                "formatter": "default",
            },
            "access": {
                "class": "logging.StreamHandler",
                "level": "INFO",
                "formatter": "access",
            },
        },
        "loggers": {
            "uvicorn": {
                "level": "INFO",
                "handlers": ["default"],
                "propagate": False,
            },
            "uvicorn.access": {
                "level": "INFO",
                "handlers": ["access"],
                "propagate": False,
            },
        },
        "root": {"level": get_log_level(), "handlers": get_handlers()},
    }
