import shutil
import uuid
from enum import Enum
from pathlib import Path
from typing import Callable

import pytest
from kiln_ai.datamodel.basemodel import KilnAttachmentModel


class MockFileFactoryMimeType(Enum):
    PDF = "application/pdf"
    PNG = "image/png"
    MP4 = "video/mp4"
    OGG = "audio/ogg"


def get_test_data_dir() -> Path:
    """
    The directory that contains test files with various mime types.

    This should not be a fixture, otherwise, any dependent tests would need to import it explicitly.
    """
    return Path(__file__).parent.parent / "data"


@pytest.fixture
def mock_file_factory(tmp_path) -> Callable[[MockFileFactoryMimeType], Path]:
    """
    Create a mock file factory that creates a mock file for the given mime type.
    The file is copied to the tmp path so it is safe to alter it without contaminating the original file.
    """

    test_data_dir = get_test_data_dir()

    def _create_mock_file(mime_type: MockFileFactoryMimeType) -> Path:
        match mime_type:
            case MockFileFactoryMimeType.PDF:
                filename = test_data_dir / "1706.03762v7.pdf"
            case MockFileFactoryMimeType.PNG:
                filename = test_data_dir / "kodim23.png"
            case MockFileFactoryMimeType.MP4:
                filename = test_data_dir / "big_buck_bunny_sample.mp4"
            case MockFileFactoryMimeType.OGG:
                filename = test_data_dir / "poacher.ogg"
            case _:
                raise ValueError(f"No test file found for mime type: {mime_type}")

        # copy the file to the tmp path to avoid test contamination of the original file
        path_copy = tmp_path / f"{str(uuid.uuid4())}.{filename.suffix}"
        shutil.copy(filename, path_copy)

        return path_copy

    return _create_mock_file


@pytest.fixture
def mock_attachment_factory(mock_file_factory):
    """
    Create a mock attachment factory that creates a mock attachment for the given mime type.
    The attachment is created from the mock file factory. The returned attachment is not
    in a persisted state.
    """

    def _create_mock_attachment(
        mime_type: MockFileFactoryMimeType,
    ) -> KilnAttachmentModel:
        path = mock_file_factory(mime_type)
        return KilnAttachmentModel.from_file(path)

    return _create_mock_attachment
