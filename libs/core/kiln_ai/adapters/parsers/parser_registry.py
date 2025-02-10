from typing import Type

from kiln_ai.adapters.ml_model_list import ModelParserID
from kiln_ai.adapters.parsers.base_parser import BaseParser
from kiln_ai.adapters.parsers.r1_parser import R1ThinkingParser
from kiln_ai.utils.exhaustive_error import raise_exhaustive_enum_error


def model_parser_from_id(parser_id: ModelParserID | None) -> Type[BaseParser]:
    """
    Get a model parser from its ID.
    """
    match parser_id:
        case None:
            return BaseParser
        case ModelParserID.r1_thinking:
            return R1ThinkingParser
        case _:
            raise_exhaustive_enum_error(parser_id)
