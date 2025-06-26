import pytest

from kiln_ai.adapters.chunkers.fixed_window_chunker import FixedWindowChunker
from kiln_ai.adapters.chunkers.registry import chunker_adapter_from_type
from kiln_ai.datamodel.chunk import ChunkerConfig, ChunkerType


def test_chunker_adapter_from_type():
    chunker = chunker_adapter_from_type(
        ChunkerType.FIXED_WINDOW,
        ChunkerConfig(
            name="test-chunker",
            chunker_type=ChunkerType.FIXED_WINDOW,
            properties={
                # do not use these values in production!
                "chunk_size": 5555,
                "chunk_overlap": 1111,
            },
        ),
    )
    assert isinstance(chunker, FixedWindowChunker)
    assert chunker.chunker_config.properties.chunk_size == 5555
    assert chunker.chunker_config.properties.chunk_overlap == 1111


def test_chunker_adapter_from_type_invalid():
    with pytest.raises(ValueError):
        chunker_adapter_from_type("invalid-type", {})
