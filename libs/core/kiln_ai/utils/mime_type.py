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


def guess_extension(mime_type: str) -> str | None:
    mapping = {
        "application/pdf": ".pdf",
        "image/png": ".png",
        "video/mp4": ".mp4",
        "audio/ogg": ".ogg",
        "text/markdown": ".md",
        "text/plain": ".txt",
        "text/html": ".html",
        "text/csv": ".csv",
        "image/jpeg": ".jpeg",
        "image/jpg": ".jpeg",
        "audio/mpeg": ".mp3",
        "audio/wav": ".wav",
        "video/quicktime": ".mov",
    }
    return mapping.get(mime_type)
