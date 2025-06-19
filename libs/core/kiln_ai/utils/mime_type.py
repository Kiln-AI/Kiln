import mimetypes


def guess_mime_type(filename: str) -> str | None:
    filename_normalized = filename.lower()

    # we override the mimetypes.guess_type for some common cases
    # because it does not handle them correctly
    if filename_normalized.endswith(".mov"):
        return "video/quicktime"
    elif filename_normalized.endswith(".mp3"):
        return "audio/mpeg"
    elif filename_normalized.endswith(".wav"):
        return "audio/wav"
    elif filename_normalized.endswith(".mp4"):
        return "video/mp4"

    mime_type, _ = mimetypes.guess_type(filename_normalized)
    return mime_type
