import mimetypes
import pathlib

"""
Utility functions for file operations used by the extractors framework.

This module provides common functionality for loading files as bytes or text,
and for determining MIME types.
"""


def load_file_bytes(path: str) -> bytes:
    """
    Reads the entire contents of a file and returns them as bytes.

    Args:
        path: Path to the file to be read.

    Returns:
        The contents of the file as a bytes object.
    """
    try:
        return pathlib.Path(path).read_bytes()
    except Exception as e:
        raise ValueError(f"Error loading file bytes for {path}: {e}") from e


def load_file_text(path: str) -> str:
    """
    Reads the entire contents of a file and returns it as a string.

    Args:
        path: The path to the file to be read.

    Returns:
        The contents of the file as a string.
    """
    try:
        return pathlib.Path(path).read_text(encoding="utf-8")
    except Exception as e:
        raise ValueError(f"Error loading file text for {path}: {e}") from e


def get_mime_type(path: str) -> str:
    """
    Determines the MIME type of a file based on its path.

    Args:
        path: The path to the file whose MIME type is to be determined.

    Returns:
        The MIME type string of the file.

    Raises:
        ValueError: If the MIME type cannot be determined from the file path.
    """
    mimetype, _ = mimetypes.guess_type(path)
    if mimetype is None:
        raise ValueError(f"Could not guess mime type for {path}")
    return mimetype
