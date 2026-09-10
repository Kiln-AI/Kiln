"""
Chunkers for processing different document types.

This package provides a framework for chunking text into smaller chunks.
"""

import os

from kiln_ai.utils.config import Config

from . import base_chunker, chunker_registry, fixed_window_chunker, semantic_chunker

# The sentence splitters need an NLTK corpus. When NLTK_DATA is unset, llama_index
# falls back to a copy bundled inside its own install directory, which uv installs as
# a hard link to save space. NLTK refuses to read a file with more than one hard link,
# so that fallback fails. Point at a writeable cache dir instead, which is what the
# desktop app already does at startup. setdefault so an existing value always wins.
os.environ.setdefault(
    "NLTK_DATA", os.path.join(Config.settings_dir(), "cache", "nltk_data")
)

__all__ = [
    "base_chunker",
    "chunker_registry",
    "fixed_window_chunker",
    "semantic_chunker",
]
