import json
from typing import Dict, Protocol

from kiln_ai.adapters.ml_model_list import ModelFormatterID
from kiln_ai.utils.exhaustive_error import raise_exhaustive_enum_error


class RequestFormatter(Protocol):
    def format_input(self, original_input: Dict | str) -> Dict | str:
        """
        Method for formatting the input to a model.
        """
        ...


class Qwen3StyleNoThinkFormatter:
    def format_input(self, original_input: Dict | str) -> Dict | str:
        """
        Format the input to a model for Qwen3 /no_think instruction
        """
        formatted_input = (
            original_input
            if isinstance(original_input, str)
            else json.dumps(original_input, indent=2)
        )

        return formatted_input + "\n\n/no_think"


def request_formatter_from_id(
    formatter_id: ModelFormatterID,
) -> RequestFormatter:
    """
    Get a model parser from its ID.
    """
    match formatter_id:
        case ModelFormatterID.qwen3_style_no_think:
            return Qwen3StyleNoThinkFormatter()
        case _:
            raise_exhaustive_enum_error(formatter_id)
