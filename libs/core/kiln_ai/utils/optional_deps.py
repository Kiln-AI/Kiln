"""
Utilities for handling optional dependencies.

This module provides helpers for lazily importing optional dependencies
with clear error messages when they're not installed.
"""

from __future__ import annotations

import importlib
from typing import Any


class MissingDependencyError(ImportError):
    """Raised when an optional dependency is not installed."""

    pass


# Map of extra names to their pip install commands
EXTRA_INSTALL_COMMANDS = {
    "rag": "kiln-ai[rag]",
    "vertex": "kiln-ai[vertex]",
}


def lazy_import(module_path: str, extra: str) -> Any:
    """
    Lazily import an optional dependency module.

    Use with TYPE_CHECKING for full type hint support:

        from __future__ import annotations
        from typing import TYPE_CHECKING

        if TYPE_CHECKING:
            from llama_index.vector_stores.lancedb import LanceDBVectorStore

        def create_store() -> LanceDBVectorStore:
            mod = lazy_import("llama_index.vector_stores.lancedb", "rag")
            return mod.LanceDBVectorStore(...)

    Args:
        module_path: Full dotted module path (e.g., "llama_index.vector_stores.lancedb")
        extra: The pip extra name for error message (e.g., "rag", "vertex")

    Returns:
        The imported module

    Raises:
        MissingDependencyError: If the module cannot be imported
    """
    try:
        return importlib.import_module(module_path)
    except ImportError as e:
        package = module_path.split(".")[0]
        install_cmd = EXTRA_INSTALL_COMMANDS.get(extra, f"kiln-ai[{extra}]")
        raise MissingDependencyError(
            f"This feature requires the '{package}' package. "
            f"Install it with: pip install {install_cmd}"
        ) from e
