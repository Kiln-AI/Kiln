from enum import Enum


class MockFileFactoryMimeType(str, Enum):
    # documents
    PDF = "application/pdf"
    CSV = "text/csv"
    TXT = "text/plain"
    HTML = "text/html"
    MD = "text/markdown"

    # images
    PNG = "image/png"
    JPG = "image/jpeg"
    JPEG = "image/jpeg"

    # audio
    MP3 = "audio/mpeg"
    WAV = "audio/wav"
    OGG = "audio/ogg"

    # video
    MP4 = "video/mp4"
    MOV = "video/quicktime"
