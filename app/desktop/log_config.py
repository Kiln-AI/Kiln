import datetime
import json
import logging
import logging.handlers
import os
from enum import Enum
from typing import List

import litellm
from kiln_ai.utils.config import Config
from litellm.integrations.custom_logger import CustomLogger
from litellm.litellm_core_utils.litellm_logging import Logging


class LogDestination(Enum):
    CONSOLE = "console"
    FILE = "file"
    ALL = "all"


def get_log_level() -> str:
    return os.getenv("KILN_LOG_LEVEL", "WARNING")


def get_log_file_path(filename: str) -> str:
    """Get the path to the log file, using environment override if specified.

    Returns:
        str: The path to the log file
    """
    log_path_default = os.path.join(Config.settings_dir(), "logs", filename)
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
        },
        "root": {"level": get_log_level(), "handlers": get_handlers()},
    }


class CustomLiteLLMLogger(CustomLogger):
    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def log_pre_api_call(self, model, messages, kwargs):
        api_base = kwargs.get("litellm_params", {}).get("api_base", "")
        headers = kwargs.get("additional_args", {}).get("headers", {})
        data = kwargs.get("additional_args", {}).get("complete_input_dict", {})

        try:
            # Print the curl command for the request
            logger = Logging(
                model=model,
                messages=messages,
                stream=False,
                call_type="completion",
                start_time=datetime.datetime.now(),
                litellm_call_id="",
                function_id="na",
                kwargs=kwargs,
            )
            curl_command = logger._get_request_curl_command(
                api_base=api_base,
                headers=headers,
                additional_args=kwargs,
                data=data,
            )
            self.logger.info(f"{curl_command}")
        except Exception as e:
            self.logger.info(f"Curl Command: Could not print {e}")

        # Print the formatted input data for the request in API format, pretty print
        try:
            self.logger.info(
                f"Formatted Input Data (API):\n{json.dumps(data, indent=2)}"
            )
        except Exception as e:
            self.logger.info(f"Formatted Input Data (API): Could not print {e}")

        # Print the messages for the request in LiteLLM Message list, pretty print
        try:
            json_messages = json.dumps(messages, indent=2)
            self.logger.info(f"Messages:\n{json_messages}")
        except Exception as e:
            self.logger.info(f"Messages: Could not print {e}")

    def log_post_api_call(self, kwargs, response_obj, start_time, end_time):
        # No op
        pass

    def log_success_event(self, kwargs, response_obj, start_time, end_time):
        litellm_logger = logging.getLogger("LiteLLM")
        litellm_logger.error(
            "Used a sync call in Litellm. Kiln should use async calls."
        )

    def log_failure_event(self, kwargs, response_obj, start_time, end_time):
        litellm_logger = logging.getLogger("LiteLLM")
        litellm_logger.error(
            "Used a sync call in Litellm. Kiln should use async calls."
        )

    #### ASYNC #### - for acompletion/aembeddings

    async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
        try:
            if len(response_obj.choices) == 1:
                if response_obj.choices[0].message.tool_calls:
                    for tool_call in response_obj.choices[0].message.tool_calls:
                        try:
                            args = tool_call.function.arguments
                            function_name = tool_call.function.name
                            self.logger.info(
                                f"Model Response Tool Call Arguments [{function_name}]:\n{args}"
                            )
                        except Exception:
                            self.logger.info(f"Model Response Tool Call:\n{tool_call}")

                content = response_obj.choices[0].message.content
                if content:
                    try:
                        # JSON format logs if possible
                        json_content = json.loads(content)
                        self.logger.info(
                            f"Model Response Content:\n{json.dumps(json_content, indent=2)}"
                        )
                    except Exception:
                        self.logger.info(f"Model Response Content:\n{content}")
            elif len(response_obj.choices) > 1:
                self.logger.info(
                    f"Model Response (multiple choices):\n{response_obj.choices}"
                )
            else:
                self.logger.info("Model Response: No choices returned")

        except Exception as e:
            self.logger.info(f"Model Response: Could not print {e}")

    async def async_log_failure_event(self, kwargs, response_obj, start_time, end_time):
        self.logger.info(f"LiteLLM Failure: {response_obj}")


def setup_litellm_logging():
    # Check if we already have a custom litellm logger
    for callback in litellm.callbacks or []:
        if isinstance(callback, CustomLiteLLMLogger):
            return  # We already have a custom litellm logger

    # If we don't have a custom litellm logger, create one
    # Disable the default litellm logger except for errors. It's ugly, hard to use, and we don't want it to mix with kiln logs.
    litellm_logger = logging.getLogger("LiteLLM")
    litellm_logger.setLevel(logging.ERROR)

    # Create a logger that logs to files, with a max size of 5MB and 3 backup files
    handler = logging.handlers.RotatingFileHandler(
        get_log_file_path("model_calls.log"),
        maxBytes=5 * 1024 * 1024,  # 5MB
        backupCount=3,
    )

    # Set formatter to match the default formatting
    formatter = logging.Formatter(get_default_formatter())
    handler.setFormatter(formatter)

    # Create a new logger for model calls
    model_calls_logger = logging.getLogger("ModelCalls")
    model_calls_logger.setLevel(logging.INFO)
    model_calls_logger.propagate = False  # Only log to file
    model_calls_logger.addHandler(handler)

    # Tell litellm to use our custom logger
    litellm.callbacks = [CustomLiteLLMLogger(model_calls_logger)]
