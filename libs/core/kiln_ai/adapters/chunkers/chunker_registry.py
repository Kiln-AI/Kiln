from kiln_ai.adapters.chunkers.base_chunker import BaseChunker
from kiln_ai.adapters.chunkers.fixed_window_chunker import FixedWindowChunker
from kiln_ai.adapters.chunkers.semantic_chunker import SemanticChunker
from kiln_ai.datamodel.chunk import ChunkerConfig, ChunkerType
from kiln_ai.utils.exhaustive_error import raise_exhaustive_enum_error


def chunker_adapter_from_type(
    chunker_type: ChunkerType,
    chunker_config: ChunkerConfig,
) -> BaseChunker:
    match chunker_type:
        case ChunkerType.FIXED_WINDOW:
            return FixedWindowChunker(chunker_config)
        case ChunkerType.SEMANTIC:
            return SemanticChunker(chunker_config)
        case _:
            # type checking will catch missing cases
            raise_exhaustive_enum_error(chunker_type)
