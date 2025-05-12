import mimetypes
import pathlib


def load_file_bytes(path: str) -> bytes:
    try:
        return pathlib.Path(path).read_bytes()
    except Exception as e:
        raise ValueError(f"Error loading file bytes for {path}: {e}") from e


def load_file_text(path: str) -> str:
    try:
        return pathlib.Path(path).read_text(encoding="utf-8")
    except Exception as e:
        raise ValueError(f"Error loading file text for {path}: {e}") from e


def get_mime_type(path: str) -> str:
    mimetype, _ = mimetypes.guess_type(path)
    if mimetype is None:
        raise ValueError(f"Could not guess mime type for {path}")
    return mimetype
