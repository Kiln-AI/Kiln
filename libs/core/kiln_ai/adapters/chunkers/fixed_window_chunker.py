import os
from pathlib import Path
from typing import List

import nltk
from llama_index.core.text_splitter import SentenceSplitter

from kiln_ai.adapters.chunkers.base_chunker import (
    BaseChunker,
    ChunkingResult,
    TextChunk,
)
from kiln_ai.datamodel.chunk import ChunkerConfig, ChunkerType
from kiln_ai.utils.config import Config


def setup_nltk_cache_dir():
    """
    Setup the nltk cache directory to a directory we know we can write to on all platforms.
    """
    nltk_data_dir = Path(Config.shared().settings_dir()) / "cache" / "nltk_data"
    nltk.data.path = [nltk_data_dir]
    os.makedirs(nltk_data_dir, exist_ok=True)

    # Download the stopwords corpus, needed by the SentenceSplitter
    # No-op if the corpus is already downloaded.
    nltk.download("stopwords", download_dir=nltk_data_dir)


class FixedWindowChunker(BaseChunker):
    def __init__(self, chunker_config: ChunkerConfig):
        if chunker_config.chunker_type != ChunkerType.FIXED_WINDOW:
            raise ValueError("Chunker type must be FIXED_WINDOW")

        chunk_size = chunker_config.chunk_size()
        if chunk_size is None:
            raise ValueError("Chunk size must be set")

        chunk_overlap = chunker_config.chunk_overlap()
        if chunk_overlap is None:
            raise ValueError("Chunk overlap must be set")

        super().__init__(chunker_config)

        setup_nltk_cache_dir()

        self.splitter = SentenceSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

    async def _chunk(self, text: str) -> ChunkingResult:
        sentences = self.splitter.split_text(text)

        chunks: List[TextChunk] = []
        for sentence in sentences:
            chunks.append(TextChunk(text=sentence))

        return ChunkingResult(chunks=chunks)
