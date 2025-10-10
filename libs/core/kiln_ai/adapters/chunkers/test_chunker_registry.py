from unittest.mock import patch

import pytest

from kiln_ai.adapters.chunkers.chunker_registry import chunker_adapter_from_type
from kiln_ai.adapters.chunkers.fixed_window_chunker import FixedWindowChunker
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
    assert chunker.chunker_config.chunk_size() == 5555
    assert chunker.chunker_config.chunk_overlap() == 1111


def test_chunker_adapter_from_type_invalid():
    with pytest.raises(ValueError):
        chunker_adapter_from_type("invalid-type", {})


def test_chunker_registry_semantic_returns_semantic_chunker():
    config = ChunkerConfig(
        name="cfg",
        chunker_type=ChunkerType.SEMANTIC,
        properties={
            "embedding_config_id": "emb-1",
            "buffer_size": 2,
            "breakpoint_percentile_threshold": 90,
            "include_metadata": True,
            "include_prev_next_rel": True,
        },
    )

    with patch(
        "kiln_ai.adapters.chunkers.chunker_registry.SemanticChunker"
    ) as mock_semantic_chunker:
        instance = chunker_adapter_from_type(ChunkerType.SEMANTIC, config)
        mock_semantic_chunker.assert_called_once_with(config)
        assert instance == mock_semantic_chunker.return_value
