import os
import re
import stat
import sys
import time
from pathlib import Path

import pytest

from kiln_mcp_server.api_tool.tmp_files import TmpFileError, TmpFileStore

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="POSIX modes")


@pytest.fixture
def root(tmp_path) -> Path:
    return tmp_path / "kiln_mcp"


@pytest.fixture
def store(root) -> TmpFileStore:
    return TmpFileStore(root)


def mode(path: Path) -> int:
    return stat.S_IMODE(os.lstat(path).st_mode)


def test_the_constructor_touches_no_disk(root):
    TmpFileStore(root)
    assert not root.exists()


@posix_only
def test_the_folder_and_files_are_private(store, root):
    saved = store.save("{}", is_json=True)
    assert mode(root) == 0o700
    assert mode(saved.path) == 0o600


@posix_only
def test_an_existing_folder_is_made_private(store, root):
    root.mkdir(mode=0o755)
    store.save("x", is_json=False)
    assert mode(root) == 0o700


@pytest.mark.parametrize("is_json, suffix", [(True, ".json"), (False, ".txt")])
def test_name_and_extension(store, root, is_json, suffix):
    saved = store.save("x", is_json=is_json)
    assert saved.path.parent == root
    assert re.fullmatch(
        rf"kiln_api_\d{{8}}_\d{{6}}_[0-9a-f]{{8}}{re.escape(suffix)}", saved.path.name
    )


@pytest.mark.windows_ci
def test_text_is_written_as_utf8_and_size_is_in_bytes(store):
    saved = store.save('{"name":"é"}', is_json=True)
    assert saved.path.read_bytes() == '{"name":"é"}'.encode()
    assert saved.size_bytes == 13


def test_each_save_gets_a_new_file(store):
    assert store.save("a", True).path != store.save("b", True).path


def test_purge_all_removes_files_and_leaves_folders(store, root):
    saved = store.save("a", True)
    (root / "sub").mkdir()
    (root / "sub" / "keep.txt").write_text("k")
    store.purge_all()
    assert not saved.path.exists()
    assert (root / "sub" / "keep.txt").exists()


def test_purge_expired_removes_only_old_files(root):
    store = TmpFileStore(root, max_age_seconds=3600)
    old = store.save("old", True)
    new = store.save("new", True)
    two_hours_ago = time.time() - 7200
    os.utime(old.path, (two_hours_ago, two_hours_ago))
    store.purge_expired()
    assert not old.path.exists()
    assert new.path.exists()


@posix_only
def test_purges_do_not_follow_symlinks(store, root, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("keep")
    store.save("a", True)
    (root / "link").symlink_to(outside)
    store.purge_all()
    assert outside.exists()


@posix_only
def test_a_symlinked_folder_is_refused(store, root, tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    root.symlink_to(real)
    with pytest.raises(TmpFileError, match="is not a folder owned by the current user"):
        store.save("a", True)


def test_a_file_in_place_of_the_folder_is_refused(store, root):
    root.write_text("not a folder")
    with pytest.raises(TmpFileError):
        store.save("a", True)


@posix_only
def test_a_folder_of_another_user_is_refused(store, root, monkeypatch):
    root.mkdir()
    real_lstat = os.lstat

    def foreign_lstat(path, *args, **kwargs):
        info = real_lstat(path, *args, **kwargs)
        if Path(path) == root:
            return os.stat_result((info.st_mode, 0, 0, 0, os.getuid() + 1, *info[5:]))
        return info

    monkeypatch.setattr(os, "lstat", foreign_lstat)
    with pytest.raises(TmpFileError):
        store.save("a", True)
    store.purge_all()


def test_purges_of_a_missing_folder_do_nothing(store, root):
    store.purge_all()
    store.purge_expired()
    assert not root.exists()


def test_purges_of_a_refused_folder_log_a_warning(store, root, caplog):
    root.write_text("not a folder")
    store.purge_all()
    assert "Not purging MCP temp files" in caplog.text
    assert root.read_text() == "not a folder"
