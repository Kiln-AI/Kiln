"""
Chunkers for processing different document types.

This package provides a framework for chunking text into smaller chunks.
"""

from . import base_chunker, chunker_registry

# Import chunkers that may have optional dependencies only when needed
__all__ = [
    "base_chunker",
    "chunker_registry",
]
