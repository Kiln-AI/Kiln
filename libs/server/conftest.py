import shutil
import uuid
from pathlib import Path
from typing import Callable

import pytest
from kiln_ai.pytest_mock_files import MockFileFactoryMimeType


@pytest.fixture
def test_data_dir() -> Path:
    """
    The directory that contains test files with various mime types.
    """
    return Path(__file__).resolve().parent.parent / "core" / "tests" / "assets"


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

        path_copy = tmp_path / f"{uuid.uuid4()!s}.{filename.suffix}"
        shutil.copy(filename, path_copy)

        return path_copy

    return create_file
