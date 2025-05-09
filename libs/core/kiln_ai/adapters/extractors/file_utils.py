import mimetypes
import pathlib


def load_file_bytes(path: str) -> bytes:
    """
    Reads the entire contents of a file and returns them as bytes.

    Args:
        path: Path to the file to be read.

    Returns:
        The contents of the file as a bytes object.
    """
    return pathlib.Path(path).read_bytes()


def load_file_text(path: str) -> str:
    """
    Reads the entire contents of a file and returns it as a string.

    Args:
        path: The path to the file to be read.

    Returns:
        The contents of the file as a string.
    """
    return pathlib.Path(path).read_text()


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
