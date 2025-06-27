from pathlib import Path

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
