"""
Chunkers for processing different document types.

This package provides a framework for chunking text into smaller chunks.

Note: Chunker implementations require the 'rag' optional dependencies.
Install with: pip install kiln-ai[rag]

The base_chunker module is always available. Implementation modules
(fixed_window_chunker, semantic_chunker) require optional dependencies.
"""

from . import base_chunker, chunker_registry

__all__ = [
    "base_chunker",
    "chunker_registry",
]
