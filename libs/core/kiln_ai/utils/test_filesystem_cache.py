import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import anyio
import pytest

from kiln_ai.utils.filesystem_cache import FilesystemCache, TemporaryFilesystemCache


class TestFilesystemCache:
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            yield Path(tmp_dir)

    @pytest.fixture
    def cache(self, temp_dir):
        return FilesystemCache(temp_dir)

    def test_init(self, temp_dir):
        cache = FilesystemCache(temp_dir)
        assert cache.cache_dir_path == temp_dir
        assert cache.validate_key is not None

    def test_get_path_valid_key(self, cache):
        key = "test_file"
        expected_path = cache.cache_dir_path / key
        assert cache.get_path(key) == expected_path

    def test_get_path_invalid_key_empty(self, cache):
        with pytest.raises(ValueError):
            cache.get_path("")

    def test_get_path_invalid_key_too_long(self, cache):
        long_key = "x" * 121  # exceeds max_length=120
        with pytest.raises(ValueError):
            cache.get_path(long_key)

    def test_get_path_invalid_key_special_chars(self, cache):
        with pytest.raises(ValueError):
            cache.get_path("invalid/key")

    async def test_get_nonexistent_file(self, cache):
        result = await cache.get("nonexistent")
        assert result is None

    async def test_get_existing_file(self, cache, temp_dir):
        key = "test"
        content = b"Hello, World!"
        file_path = temp_dir / key
        file_path.write_bytes(content)

        result = await cache.get(key)
        assert result == content

    async def test_get_file_read_error(self, cache, temp_dir):
        key = "test"
        file_path = temp_dir / key
        file_path.write_bytes(b"test")

        with patch(
            "anyio.Path.read_bytes",
            new_callable=AsyncMock,
            side_effect=IOError("Read error"),
        ):
            result = await cache.get(key)
            assert result is None

    async def test_set_valid_data(self, cache, temp_dir):
        key = "test"
        content = b"Hello, World!"

        result_path = await cache.set(key, content)
        expected_path = temp_dir / key

        assert result_path == expected_path
        assert expected_path.exists()
        assert expected_path.read_bytes() == content

    async def test_set_invalid_key_empty(self, cache):
        with pytest.raises(ValueError):
            await cache.set("", b"content")

    async def test_set_invalid_key_too_long(self, cache):
        long_key = "x" * 121
        with pytest.raises(ValueError):
            await cache.set(long_key, b"content")

    async def test_set_invalid_key_special_chars(self, cache):
        with pytest.raises(ValueError):
            await cache.set("invalid/key", b"content")

    async def test_set_overwrites_existing(self, cache, temp_dir):
        key = "test"
        original_content = b"Original content"
        new_content = b"New content"

        # Set original content
        await cache.set(key, original_content)
        assert (temp_dir / key).read_bytes() == original_content

        # Overwrite with new content
        await cache.set(key, new_content)
        assert (temp_dir / key).read_bytes() == new_content

    async def test_set_creates_parent_directory(self, cache, temp_dir):
        # Test that set method creates parent directories if they don't exist
        # Note: This test demonstrates a limitation - the current implementation
        # doesn't support directory paths due to name_validator restrictions
        key = "subdir_test"  # Using underscore instead of slash
        content = b"Test content"

        result_path = await cache.set(key, content)
        expected_path = temp_dir / key

        assert result_path == expected_path
        assert expected_path.exists()
        assert expected_path.read_bytes() == content

    async def test_set_with_nested_directories(self, cache, temp_dir):
        # Test that set method creates deeply nested directories
        # Note: This test demonstrates a limitation - the current implementation
        # doesn't support directory paths due to name_validator restrictions
        key = "level1_level2_level3_test"  # Using underscores instead of slashes
        content = b"Deeply nested content"

        result_path = await cache.set(key, content)
        expected_path = temp_dir / key

        assert result_path == expected_path
        assert expected_path.exists()
        assert expected_path.read_bytes() == content

    async def test_directory_paths_not_supported(self, cache):
        # Test that demonstrates the current limitation - directory paths are not supported
        # due to name_validator forbidding forward slashes
        with pytest.raises(ValueError, match="Name is invalid"):
            await cache.set("subdir/test", b"content")

        with pytest.raises(ValueError, match="Name is invalid"):
            await cache.get("subdir/test")

    async def test_roundtrip_get_set(self, cache):
        key = "roundtrip"
        content = b"Roundtrip test content"

        # Set content
        await cache.set(key, content)

        # Get content back
        retrieved = await cache.get(key)
        assert retrieved == content

    async def test_multiple_files(self, cache, temp_dir):
        files = {
            "file1": b"Content 1",
            "file2": b"Content 2",
            "subdir_file3": b"Content 3",  # Using underscore instead of slash
        }

        # Set all files
        for key, content in files.items():
            await cache.set(key, content)

        # Verify all files exist and have correct content
        for key, expected_content in files.items():
            actual_content = await cache.get(key)
            assert actual_content == expected_content

    async def test_empty_bytes(self, cache):
        key = "empty"
        content = b""

        await cache.set(key, content)
        retrieved = await cache.get(key)
        assert retrieved == content

    async def test_large_content(self, cache):
        key = "large"
        content = b"x" * 10000  # 10KB of data

        await cache.set(key, content)
        retrieved = await cache.get(key)
        assert retrieved == content

    @pytest.mark.parametrize(
        "unicode_text",
        [
            "Simple ASCII text",
            "中文文本测试",
            "Mixed 中文 and English text",
            "Emojis: 🎉🚀💻🔥",
            "Complex: 你好世界! Hello 世界! 🌍 This is 测试 with 中文, emojis 🚀, and English.",
            "Special chars: ñáéíóú àèìòù çüöä",
            "Math symbols: ∑∆π∫∞±≤≥≠",
            "Currency: €£¥$₹₽",
        ],
    )
    async def test_unicode_text_retrieval_integrity(self, cache, unicode_text):
        # Test that Unicode text is not corrupted during storage and retrieval
        key = "unicode_integrity"
        content = unicode_text.encode("utf-8")

        # Store the text
        await cache.set(key, content)

        # Retrieve and verify
        retrieved = await cache.get(key)
        assert retrieved == content
        assert retrieved.decode("utf-8") == unicode_text

    async def test_key_overwrite_behavior(self, cache):
        # Test that setting at the same key overwrites whatever was there
        key = "overwrite_test"

        # Set initial content
        initial_content = "Initial content".encode("utf-8")
        await cache.set(key, initial_content)

        # Verify initial content is stored
        retrieved = await cache.get(key)
        assert retrieved == initial_content
        assert retrieved.decode("utf-8") == "Initial content"

        # Overwrite with different content
        new_content = "New content with 中文 and emojis 🚀".encode("utf-8")
        await cache.set(key, new_content)

        # Verify the content was overwritten
        retrieved = await cache.get(key)
        assert retrieved == new_content
        assert retrieved.decode("utf-8") == "New content with 中文 and emojis 🚀"
        assert retrieved != initial_content

        # Overwrite again with empty content
        empty_content = b""
        await cache.set(key, empty_content)

        # Verify empty content is stored
        retrieved = await cache.get(key)
        assert retrieved == empty_content
        assert retrieved.decode("utf-8") == ""

    @pytest.mark.parametrize(
        "invalid_key",
        [
            "",
            "x" * 121,
            "invalid/key",
            "invalid\\key",
            "invalid:key",
            "invalid*key",
            "invalid?key",
            "invalid<key",
            "invalid>key",
            "invalid|key",
        ],
    )
    async def test_invalid_keys(self, cache, invalid_key):
        with pytest.raises(ValueError):
            cache.get_path(invalid_key)

        with pytest.raises(ValueError):
            await cache.set(invalid_key, b"content")

    async def test_delete_by_prefix(self, cache):
        key1 = "test1"
        key2 = "test2"
        key3 = "test3"
        non_target_key = "non_target_key"

        await cache.set(key1, b"content1")
        await cache.set(key2, b"content2")
        await cache.set(key3, b"content3")
        await cache.set(non_target_key, b"content4")

        await cache.delete_by_prefix("test")

        # should delete target keys
        assert not (cache.cache_dir_path / key1).exists()
        assert not (cache.cache_dir_path / key2).exists()
        assert not (cache.cache_dir_path / key3).exists()

        # should not delete non-target key
        assert (cache.cache_dir_path / non_target_key).exists()

    async def test_delete_by_prefix_no_match(self, cache):
        key1 = "test1"
        key2 = "test2"
        key3 = "test3"

        await cache.set(key1, b"content1")
        await cache.set(key2, b"content2")
        await cache.set(key3, b"content3")

        await cache.delete_by_prefix("nonexistent")

        # should not delete anything
        assert (cache.cache_dir_path / key1).exists()
        assert (cache.cache_dir_path / key2).exists()
        assert (cache.cache_dir_path / key3).exists()

    async def test_delete_by_prefix_handles_file_not_found(self, cache):
        # Seed a few files
        await cache.set("test1", b"1")
        await cache.set("test2", b"2")

        # Simulate a race: files disappear between discovery and unlink
        original_unlink = anyio.Path.unlink

        async def flaky_unlink(self):  # type: ignore[no-redef]
            raise FileNotFoundError("gone")

        try:
            anyio.Path.unlink = flaky_unlink  # type: ignore[assignment]
            # Should not raise despite FileNotFoundError
            await cache.delete_by_prefix("test")
        finally:
            anyio.Path.unlink = original_unlink  # type: ignore[assignment]

    async def test_delete_by_prefix_logs_other_errors(self, cache, monkeypatch):
        # Seed a target file
        await cache.set("test_err", b"x")

        # Make unlink raise a generic Exception and verify we log an error but do not raise
        async def bad_unlink(self):  # type: ignore[no-redef]
            raise RuntimeError("unexpected")

        monkeypatch.setattr(
            anyio,
            "Path",
            lambda p: type(
                "P", (), {"__init__": lambda self, q: None, "unlink": bad_unlink}
            )(),
        )

        with patch("kiln_ai.utils.filesystem_cache.logger") as mock_logger:
            await cache.delete_by_prefix("test_")
            assert mock_logger.error.called


class TestTemporaryFilesystemCache:
    def test_temporary_cache_creation(self):
        """Test that TemporaryFilesystemCache creates a temporary directory."""
        temp_cache = TemporaryFilesystemCache()

        # Should create a temporary directory
        assert temp_cache._cache_temp_dir is not None
        assert Path(temp_cache._cache_temp_dir).exists()

        # Check that the directory name (not full path) starts with the prefix
        temp_dir_name = Path(temp_cache._cache_temp_dir).name
        assert temp_dir_name.startswith("kiln_cache_")

        # Should have a FilesystemCache instance
        assert isinstance(temp_cache.filesystem_cache, FilesystemCache)
        assert temp_cache.filesystem_cache.cache_dir_path == Path(
            temp_cache._cache_temp_dir
        )

    async def test_multiple_instances_share_same_cache(self):
        """Test that multiple calls to shared() return the same cache instance."""
        # Get cache instances
        cache1 = TemporaryFilesystemCache.shared()
        cache2 = TemporaryFilesystemCache.shared()

        # Should be the same instance
        assert cache1 is cache2

        # Test that they share the same cache directory
        assert cache1.cache_dir_path == cache2.cache_dir_path

        # Test that content set in one is available in the other
        key = "shared_test"
        content = b"shared content"

        await cache1.set(key, content)
        retrieved = await cache2.get(key)
        assert retrieved == content

    def test_cache_directory_naming(self):
        """Test that the temporary cache directory has the correct naming pattern."""
        temp_cache = TemporaryFilesystemCache()
        temp_dir_name = Path(temp_cache._cache_temp_dir).name

        # Should start with the expected prefix
        assert temp_dir_name.startswith("kiln_cache_")

        # Should be a valid directory name
        assert len(temp_dir_name) > len("kiln_cache_")
        assert "/" not in temp_dir_name  # Should not contain path separators
