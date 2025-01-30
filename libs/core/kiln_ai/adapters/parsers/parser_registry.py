from typing import NoReturn, Type

from kiln_ai.adapters.ml_model_list import ModelParserID
from kiln_ai.adapters.parsers.base_parser import BaseParser
from kiln_ai.adapters.parsers.r1_parser import R1ThinkingParser


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
            # triggers pyright warning if I miss a case
            raise ValueError(
                f"Unhandled enum value for parser ID. You may need to update Kiln to work with this project. Value: {parser_id}"
            )
            return NoReturn
