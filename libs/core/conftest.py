import shutil
import uuid
from enum import Enum
from pathlib import Path
from typing import Callable

import pytest
from kiln_ai.datamodel.basemodel import KilnAttachmentModel


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


@pytest.fixture
def test_data_dir() -> Path:
    """
    The directory that contains test files with various mime types.
    """
    return Path(__file__).parent / "tests" / "assets"


@pytest.fixture
def mock_file_factory(
    tmp_path, test_data_dir
) -> Callable[[MockFileFactoryMimeType], Path]:
    """
    Create a mock file factory that creates a mock file for the given mime type.
    The file is copied to the tmp path so it is safe to alter it without contaminating the original file.
    """

    def create_file(mime_type: MockFileFactoryMimeType) -> Path:
        match mime_type:
            # document
            case MockFileFactoryMimeType.PDF:
                filename = test_data_dir / "document_paper.pdf"
            case MockFileFactoryMimeType.CSV:
                filename = test_data_dir / "document_people.csv"
            case MockFileFactoryMimeType.TXT:
                filename = test_data_dir / "document_ice_cubes.txt"
            case MockFileFactoryMimeType.HTML:
                filename = test_data_dir / "document_ice_cubes.html"
            case MockFileFactoryMimeType.MD:
                filename = test_data_dir / "document_ice_cubes.md"

            # images
            case MockFileFactoryMimeType.PNG:
                filename = test_data_dir / "image_kodim23.png"
            case MockFileFactoryMimeType.JPG:
                filename = test_data_dir / "image_nasa.jpg"
            case MockFileFactoryMimeType.JPEG:
                filename = test_data_dir / "image_nasa.jpeg"

            # audio
            case MockFileFactoryMimeType.OGG:
                filename = test_data_dir / "audio_ice_cubes.ogg"
            case MockFileFactoryMimeType.MP3:
                filename = test_data_dir / "audio_ice_cubes.mp3"
            case MockFileFactoryMimeType.WAV:
                filename = test_data_dir / "audio_ice_cubes.wav"

            # video
            case MockFileFactoryMimeType.MP4:
                filename = test_data_dir / "video_tv_bars.mp4"
            case MockFileFactoryMimeType.MOV:
                filename = test_data_dir / "video_tv_bars.mov"

            case _:
                raise ValueError(f"No test file found for mime type: {mime_type}")

        # copy the file to the tmp path to avoid test contamination of the original file
        path_copy = tmp_path / f"{uuid.uuid4()!s}.{filename.suffix}"
        shutil.copy(filename, path_copy)

        return path_copy

    return create_file


@pytest.fixture
def mock_attachment_factory(mock_file_factory):
    """
    Create a mock attachment factory that creates a mock attachment for the given mime type.
    The attachment is created from the mock file factory.
    """

    def create_attachment(
        mime_type: MockFileFactoryMimeType,
        text: str | None = None,
    ) -> KilnAttachmentModel:
        if text is not None:
            return KilnAttachmentModel.from_data(text, mime_type)

        path = mock_file_factory(mime_type)
        return KilnAttachmentModel.from_file(path)

    return create_attachment
