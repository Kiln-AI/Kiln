import json
from pathlib import Path
from unittest.mock import patch

import pygit2
import pytest

from app.desktop.git_sync.clone import (
    compute_clone_path,
    compute_temp_clone_path,
    list_remote_branches,
    rename_clone_to_final_path,
    scan_for_projects,
)
from app.desktop.git_sync.clone import test_remote_access as check_remote_access


class TestComputeClonePath:
    def test_creates_git_projects_dir(self, tmp_path: Path):
        result = compute_clone_path(tmp_path, "My Project", "abc123")
        assert result.parent.name == ".git-projects"
        assert result.parent.exists()

    def test_basic_path_format(self, tmp_path: Path):
        result = compute_clone_path(tmp_path, "My Project", "abc123")
        assert result.name == "abc123 - My Project"

    def test_collision_adds_counter(self, tmp_path: Path):
        first = compute_clone_path(tmp_path, "My Project", "abc123")
        first.mkdir(parents=True)
        second = compute_clone_path(tmp_path, "My Project", "abc123")
        assert second.name == "abc123 - My Project2"

    def test_multiple_collisions(self, tmp_path: Path):
        for i in range(3):
            path = compute_clone_path(tmp_path, "Test", "id1")
            path.mkdir(parents=True)
        result = compute_clone_path(tmp_path, "Test", "id1")
        assert result.name == "id1 - Test4"

    def test_sanitizes_special_characters(self, tmp_path: Path):
        result = compute_clone_path(tmp_path, "My/Project:Name", "id")
        assert "/" not in result.name.split(" - ", 1)[1]

    def test_empty_project_name(self, tmp_path: Path):
        result = compute_clone_path(tmp_path, "", "abc")
        assert "project" in result.name

    def test_empty_project_id(self, tmp_path: Path):
        result = compute_clone_path(tmp_path, "My Project", "")
        assert result.name == "My Project"

    def test_sanitizes_project_id(self, tmp_path: Path):
        result = compute_clone_path(tmp_path, "Test", "../../escape")
        assert "/" not in result.name
        assert ".." not in result.name


class TestComputeTempClonePath:
    def test_uses_os_temp_dir(self):
        import tempfile

        result = compute_temp_clone_path()
        assert result.exists()
        assert result.is_dir()
        assert str(result).startswith(tempfile.gettempdir())
        result.rmdir()

    def test_unique_paths(self):
        path1 = compute_temp_clone_path()
        path2 = compute_temp_clone_path()
        assert path1 != path2
        path1.rmdir()
        path2.rmdir()

    def test_path_starts_with_kiln_clone_prefix(self):
        result = compute_temp_clone_path()
        assert result.name.startswith("kiln_clone_")
        result.rmdir()


class TestRenameCloneToFinalPath:
    def test_renames_to_proper_path(self, tmp_path: Path):
        import tempfile

        temp_dir = Path(tempfile.mkdtemp(prefix="kiln_clone_"))
        (temp_dir / "marker.txt").write_text("hello")

        result = rename_clone_to_final_path(
            temp_dir, tmp_path, "My Project", "proj_123"
        )

        assert result.name == "proj_123 - My Project"
        assert result.parent.name == ".git-projects"
        assert (result / "marker.txt").read_text() == "hello"
        assert not temp_dir.exists()

    def test_raises_for_nonexistent_path(self, tmp_path: Path):
        with pytest.raises(ValueError, match="does not exist"):
            rename_clone_to_final_path(
                tmp_path / "nonexistent", tmp_path, "Test", "id1"
            )

    def test_handles_collision(self, tmp_path: Path):
        import tempfile

        existing = tmp_path / ".git-projects" / "id1 - Test"
        existing.mkdir(parents=True)

        temp_dir = Path(tempfile.mkdtemp(prefix="kiln_clone_"))

        result = rename_clone_to_final_path(temp_dir, tmp_path, "Test", "id1")
        assert result.name == "id1 - Test2"


class TestScanForProjects:
    def test_finds_single_project(self, tmp_path: Path):
        project_data = {
            "name": "Test Project",
            "description": "A test",
            "id": "proj_123",
        }
        (tmp_path / "project.kiln").write_text(json.dumps(project_data))

        results = scan_for_projects(tmp_path)
        assert len(results) == 1
        assert results[0]["name"] == "Test Project"
        assert results[0]["description"] == "A test"
        assert results[0]["path"] == "project.kiln"
        assert results[0]["id"] == "proj_123"

    def test_finds_multiple_projects(self, tmp_path: Path):
        (tmp_path / "project.kiln").write_text(json.dumps({"name": "Root Project"}))
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "project.kiln").write_text(json.dumps({"name": "Sub Project"}))

        results = scan_for_projects(tmp_path)
        assert len(results) == 2
        names = [r["name"] for r in results]
        assert "Root Project" in names
        assert "Sub Project" in names

    def test_no_projects_returns_empty(self, tmp_path: Path):
        results = scan_for_projects(tmp_path)
        assert results == []

    def test_handles_invalid_json(self, tmp_path: Path):
        (tmp_path / "project.kiln").write_text("not json")
        results = scan_for_projects(tmp_path)
        assert len(results) == 1
        assert results[0]["path"] == "project.kiln"

    def test_missing_id_defaults_to_empty(self, tmp_path: Path):
        project_data = {"name": "No ID Project"}
        (tmp_path / "project.kiln").write_text(json.dumps(project_data))

        results = scan_for_projects(tmp_path)
        assert len(results) == 1
        assert results[0]["id"] == ""

    def test_results_sorted_by_path(self, tmp_path: Path):
        for name in ["c_proj", "a_proj", "b_proj"]:
            d = tmp_path / name
            d.mkdir()
            (d / "project.kiln").write_text(json.dumps({"name": name}))

        results = scan_for_projects(tmp_path)
        paths = [r["path"] for r in results]
        assert paths == sorted(paths)


def _make_ref_dicts(refs: list[tuple[str, str | None]]) -> list[dict]:
    """Helper to build ref dicts matching Remote.ls_remotes() output."""
    result = []
    for name, symref in refs:
        result.append(
            {
                "local": False,
                "oid": pygit2.Oid(hex="a" * 40),
                "loid": None,
                "name": name,
                "symref_target": symref,
            }
        )
    return result


class TestTestRemoteAccess:
    def test_success_system_keys(self):
        with patch("app.desktop.git_sync.clone._ls_remote_pygit2") as mock:
            mock.return_value = _make_ref_dicts([("HEAD", None)])
            success, msg, mode = check_remote_access("git@github.com:org/repo.git")
            assert success is True
            assert msg == "Access successful"
            assert mode == "system_keys"

    def test_success_with_pat(self):
        with patch("app.desktop.git_sync.clone._ls_remote_pygit2") as mock:
            mock.return_value = _make_ref_dicts([("HEAD", None)])
            success, msg, mode = check_remote_access(
                "https://github.com/org/repo.git", pat_token="ghp_token"
            )
            assert success is True
            assert mode == "pat_token"

    def test_auth_failure(self):
        with patch("app.desktop.git_sync.clone._ls_remote_pygit2") as mock:
            mock.side_effect = pygit2.GitError(
                "Authentication failed for 'https://github.com/org/repo.git'"
            )
            success, msg, mode = check_remote_access("https://github.com/org/repo.git")
            assert success is False
            assert msg == "Authentication failed"
            assert mode is None

    def test_other_error(self):
        with patch("app.desktop.git_sync.clone._ls_remote_pygit2") as mock:
            mock.side_effect = pygit2.GitError("repository not found")
            success, msg, mode = check_remote_access("https://github.com/org/repo.git")
            assert success is False
            assert "repository not found" in msg
            assert mode is None

    def test_explicit_auth_mode(self):
        with patch("app.desktop.git_sync.clone._ls_remote_pygit2") as mock:
            mock.return_value = _make_ref_dicts([("HEAD", None)])
            success, msg, mode = check_remote_access(
                "https://github.com/org/repo.git",
                pat_token="ghp_token",
                auth_mode="pat_token",
            )
            assert success is True
            assert mode == "pat_token"
            mock.assert_called_once_with(
                "https://github.com/org/repo.git", "ghp_token", "pat_token"
            )


class TestListRemoteBranches:
    def test_returns_branches_and_default(self):
        refs = _make_ref_dicts(
            [
                ("HEAD", "refs/heads/main"),
                ("refs/heads/main", None),
                ("refs/heads/feature", None),
            ]
        )
        with patch("app.desktop.git_sync.clone._ls_remote_pygit2") as mock:
            mock.return_value = refs
            branches, default = list_remote_branches("https://github.com/org/repo.git")
            assert branches == ["feature", "main"]
            assert default == "main"

    def test_raises_on_failure(self):
        with patch("app.desktop.git_sync.clone._ls_remote_pygit2") as mock:
            mock.side_effect = pygit2.GitError("repository not found")
            try:
                list_remote_branches("https://github.com/org/repo.git")
                assert False, "Should have raised"
            except Exception as e:
                assert "repository not found" in str(e)

    def test_no_symref_falls_back_to_main(self):
        refs = _make_ref_dicts(
            [
                ("HEAD", None),
                ("refs/heads/main", None),
                ("refs/heads/develop", None),
            ]
        )
        with patch("app.desktop.git_sync.clone._ls_remote_pygit2") as mock:
            mock.return_value = refs
            branches, default = list_remote_branches("https://github.com/org/repo.git")
            assert default == "main"

    def test_no_symref_falls_back_to_master(self):
        refs = _make_ref_dicts(
            [
                ("HEAD", None),
                ("refs/heads/master", None),
            ]
        )
        with patch("app.desktop.git_sync.clone._ls_remote_pygit2") as mock:
            mock.return_value = refs
            branches, default = list_remote_branches("https://github.com/org/repo.git")
            assert default == "master"

    def test_ignores_tags(self):
        refs = _make_ref_dicts(
            [
                ("refs/heads/main", None),
                ("refs/tags/v1.0", None),
            ]
        )
        with patch("app.desktop.git_sync.clone._ls_remote_pygit2") as mock:
            mock.return_value = refs
            branches, _ = list_remote_branches("https://github.com/org/repo.git")
            assert branches == ["main"]
