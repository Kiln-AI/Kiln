from __future__ import annotations

from typing import TYPE_CHECKING

from kiln_ai.adapters.chunkers.base_chunker import BaseChunker
from kiln_ai.datamodel.chunk import ChunkerConfig, ChunkerType
from kiln_ai.utils.exhaustive_error import raise_exhaustive_enum_error
from kiln_ai.utils.optional_deps import lazy_import

if TYPE_CHECKING:
    from kiln_ai.adapters.chunkers.fixed_window_chunker import FixedWindowChunker
    from kiln_ai.adapters.chunkers.semantic_chunker import SemanticChunker


def chunker_adapter_from_type(
    chunker_type: ChunkerType,
    chunker_config: ChunkerConfig,
) -> BaseChunker:
    match chunker_type:
        case ChunkerType.FIXED_WINDOW:
            mod = lazy_import("kiln_ai.adapters.chunkers.fixed_window_chunker", "rag")
            FixedWindowChunker: type[FixedWindowChunker] = mod.FixedWindowChunker
            return FixedWindowChunker(chunker_config)
        case ChunkerType.SEMANTIC:
            mod = lazy_import("kiln_ai.adapters.chunkers.semantic_chunker", "rag")
            SemanticChunker: type[SemanticChunker] = mod.SemanticChunker
            return SemanticChunker(chunker_config)
        case _:
            # type checking will catch missing cases
            raise_exhaustive_enum_error(chunker_type)
