import mimetypes
import pathlib


def load_file_bytes(path: str) -> bytes:
    """
    Load a file as bytes.
    """
    return pathlib.Path(path).read_bytes()


def load_file_text(path: str) -> str:
    """
    Load a file as text.
    """
    return pathlib.Path(path).read_text()


def get_mime_type(path: str) -> str:
    """
    Get the mime type of a file.
    """
    mimetype, _ = mimetypes.guess_type(path)
    if mimetype is None:
        raise ValueError(f"Could not guess mime type for {path}")
    return mimetype
