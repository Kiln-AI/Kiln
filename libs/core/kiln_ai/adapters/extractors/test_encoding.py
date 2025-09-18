from pathlib import Path

import pytest

from conftest import MockFileFactoryMimeType
from kiln_ai.adapters.extractors.encoding import from_base64_url, to_base64_url


async def test_to_base64_url(mock_file_factory):
    mock_file = mock_file_factory(MockFileFactoryMimeType.JPEG)

    byte_data = Path(mock_file).read_bytes()

    # encode the byte data
    base64_url = to_base64_url("image/jpeg", byte_data)
    assert base64_url.startswith("data:image/jpeg;base64,")

    # decode the base64 url
    assert from_base64_url(base64_url) == byte_data


def test_from_base64_url_invalid_format_no_data_prefix():
    """Test that from_base64_url raises ValueError when input doesn't start with 'data:'"""
    with pytest.raises(ValueError, match="Invalid base64 URL format"):
        from_base64_url("not-a-data-url")


def test_from_base64_url_invalid_format_no_comma():
    """Test that from_base64_url raises ValueError when input doesn't contain a comma"""
    with pytest.raises(ValueError, match="Invalid base64 URL format"):
        from_base64_url("data:image/jpeg;base64")


def test_from_base64_url_invalid_parts():
    """Test that from_base64_url raises ValueError when splitting by comma doesn't result in exactly 2 parts"""
    with pytest.raises(ValueError, match="Invalid base64 URL format"):
        from_base64_url("data:image/jpeg;base64,part1,part2")


def test_from_base64_url_base64_decode_failure():
    """Test that from_base64_url raises ValueError when base64 decoding fails"""
    with pytest.raises(ValueError, match="Failed to decode base64 data"):
        from_base64_url("data:image/jpeg;base64,invalid-base64-data!")


def test_from_base64_url_valid_format():
    """Test that from_base64_url works with valid base64 URL format"""
    # Create a simple valid base64 URL
    test_data = b"Hello, World!"
    base64_encoded = "SGVsbG8sIFdvcmxkIQ=="
    base64_url = f"data:text/plain;base64,{base64_encoded}"

    result = from_base64_url(base64_url)
    assert result == test_data
