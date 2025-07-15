import os
import shutil
import uuid
from enum import Enum
from pathlib import Path
from typing import Callable
from unittest.mock import patch

import litellm
import pytest
from dotenv import load_dotenv
from kiln_ai.datamodel.basemodel import KilnAttachmentModel
from kiln_ai.utils.config import Config


@pytest.fixture(autouse=True)
def _clear_httpx_clients() -> None:
    litellm.in_memory_llm_clients_cache.flush_cache()


@pytest.fixture(autouse=True)
def skip_remote_model_list():
    """Set environment variable to skip remote model list fetching during tests"""
    os.environ["KILN_SKIP_REMOTE_MODEL_LIST"] = "true"
    yield
    # Clean up after the test
    if "KILN_SKIP_REMOTE_MODEL_LIST" in os.environ:
        del os.environ["KILN_SKIP_REMOTE_MODEL_LIST"]


@pytest.fixture(scope="session", autouse=True)
def load_env():
    load_dotenv()


# mock out the settings path so we don't clobber the user's actual settings during tests
@pytest.fixture(autouse=True)
def use_temp_settings_dir(tmp_path):
    with patch.object(
        Config, "settings_path", return_value=str(tmp_path / "settings.yaml")
    ):
        yield


@pytest.fixture(scope="session", autouse=True)
def setup_test_logging():
    from kiln_ai.utils.logging import setup_litellm_logging

    setup_litellm_logging("test_model_calls.log")
    yield


def pytest_addoption(parser):
    parser.addoption(
        "--runpaid",
        action="store_true",
        default=False,
        help="run tests that make paid API calls",
    )
    parser.addoption(
        "--runsinglewithoutchecks",
        action="store_true",
        default=False,
        help="if testing a single test, don't check for skips like runpaid",
    )
    parser.addoption(
        "--ollama",
        action="store_true",
        default=False,
        help="run tests that use ollama server",
    )


def is_single_manual_test(config, items) -> bool:
    # Check if we're running manually (eg, in vscode)
    if not config.getoption("--runsinglewithoutchecks"):
        return False

    if len(items) == 1:
        return True
    if len(items) == 0:
        return False

    # Check if all of the items are the same prefix, expluding a.b.c[param]
    # This is still a 'single test' for the purposes of this flag
    prefix = items[0].name.split("[")[0] + "["
    for item in items:
        if not item.name.startswith(prefix):
            return False
    return True


def pytest_collection_modifyitems(config, items):
    # Always run test if it's a single test manually invoked
    if is_single_manual_test(config, items):
        return

    # Mark tests that use paid services as skipped unless --runpaid is passed
    if not config.getoption("--runpaid"):
        skip_paid = pytest.mark.skip(reason="need --runpaid option to run")
        for item in items:
            if "paid" in item.keywords:
                item.add_marker(skip_paid)

    # Mark tests that use ollama server as skipped unless --ollama is passed
    if not config.getoption("--ollama"):
        skip_ollama = pytest.mark.skip(reason="need --ollama option to run")
        for item in items:
            if "ollama" in item.keywords:
                item.add_marker(skip_ollama)


class MockFileFactoryMimeType(Enum):
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
            case MockFileFactoryMimeType.TXT:
                filename = test_data_dir / "document_ice_cubes.txt"

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
        path_copy = tmp_path / f"{str(uuid.uuid4())}.{filename.suffix}"
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
    ) -> KilnAttachmentModel:
        path = mock_file_factory(mime_type)
        return KilnAttachmentModel.from_file(path)

    return create_attachment
