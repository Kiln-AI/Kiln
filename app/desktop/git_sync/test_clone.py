import json
import subprocess
from pathlib import Path
from unittest.mock import patch

from app.desktop.git_sync.clone import (
    _build_authenticated_url,
    _parse_ls_remote_output,
    compute_clone_path,
    list_remote_branches,
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


class TestBuildAuthenticatedUrl:
    def test_no_token(self):
        assert _build_authenticated_url("https://github.com/org/repo.git", None) == (
            "https://github.com/org/repo.git"
        )

    def test_https_with_token(self):
        result = _build_authenticated_url(
            "https://github.com/org/repo.git", "ghp_abc123"
        )
        assert result == "https://x-token:ghp_abc123@github.com/org/repo.git"

    def test_non_https_unchanged(self):
        result = _build_authenticated_url("git@github.com:org/repo.git", "ghp_abc123")
        assert result == "git@github.com:org/repo.git"


class TestParseLsRemoteOutput:
    def test_basic_output(self):
        output = (
            "ref: refs/heads/main\tHEAD\n"
            "abc123\tHEAD\n"
            "abc123\trefs/heads/main\n"
            "def456\trefs/heads/develop\n"
            "ghi789\trefs/heads/feature\n"
        )
        branches, default = _parse_ls_remote_output(output)
        assert branches == ["develop", "feature", "main"]
        assert default == "main"

    def test_no_symref_falls_back_to_main(self):
        output = "abc123\tHEAD\nabc123\trefs/heads/main\ndef456\trefs/heads/develop\n"
        branches, default = _parse_ls_remote_output(output)
        assert branches == ["develop", "main"]
        assert default == "main"

    def test_no_symref_falls_back_to_master(self):
        output = "abc123\tHEAD\nabc123\trefs/heads/master\n"
        branches, default = _parse_ls_remote_output(output)
        assert branches == ["master"]
        assert default == "master"

    def test_no_symref_no_main_or_master(self):
        output = "abc123\tHEAD\nabc123\trefs/heads/develop\n"
        branches, default = _parse_ls_remote_output(output)
        assert branches == ["develop"]
        assert default is None

    def test_ignores_tags_and_other_refs(self):
        output = (
            "abc123\trefs/heads/main\n"
            "def456\trefs/tags/v1.0\n"
            "ghi789\trefs/pull/1/head\n"
        )
        branches, default = _parse_ls_remote_output(output)
        assert branches == ["main"]

    def test_empty_output(self):
        branches, default = _parse_ls_remote_output("")
        assert branches == []
        assert default is None


class TestTestRemoteAccess:
    def test_success(self):
        with patch("app.desktop.git_sync.clone._run_git_ls_remote") as mock:
            mock.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="abc\tHEAD\n", stderr=""
            )
            success, msg = check_remote_access("https://github.com/org/repo.git")
            assert success is True
            assert msg == "Access successful"

    def test_auth_failure(self):
        with patch("app.desktop.git_sync.clone._run_git_ls_remote") as mock:
            mock.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=128,
                stdout="",
                stderr="fatal: Authentication failed for 'https://github.com/org/repo.git'",
            )
            success, msg = check_remote_access("https://github.com/org/repo.git")
            assert success is False
            assert msg == "Authentication required"

    def test_other_error(self):
        with patch("app.desktop.git_sync.clone._run_git_ls_remote") as mock:
            mock.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=128,
                stdout="",
                stderr="fatal: repository not found",
            )
            success, msg = check_remote_access("https://github.com/org/repo.git")
            assert success is False
            assert "repository not found" in msg

    def test_timeout(self):
        with patch("app.desktop.git_sync.clone._run_git_ls_remote") as mock:
            mock.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=30)
            success, msg = check_remote_access("https://github.com/org/repo.git")
            assert success is False
            assert "timed out" in msg

    def test_passes_pat_token(self):
        with patch("app.desktop.git_sync.clone._run_git_ls_remote") as mock:
            mock.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="abc\tHEAD\n", stderr=""
            )
            check_remote_access("https://github.com/org/repo.git", "ghp_token")
            mock.assert_called_once_with("https://github.com/org/repo.git", "ghp_token")


class TestListRemoteBranches:
    def test_returns_branches_and_default(self):
        ls_output = (
            "ref: refs/heads/main\tHEAD\n"
            "abc123\tHEAD\n"
            "abc123\trefs/heads/main\n"
            "def456\trefs/heads/feature\n"
        )
        with patch("app.desktop.git_sync.clone._run_git_ls_remote") as mock:
            mock.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout=ls_output, stderr=""
            )
            branches, default = list_remote_branches("https://github.com/org/repo.git")
            assert branches == ["feature", "main"]
            assert default == "main"

    def test_raises_on_failure(self):
        with patch("app.desktop.git_sync.clone._run_git_ls_remote") as mock:
            mock.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=128,
                stdout="",
                stderr="fatal: repository not found",
            )
            try:
                list_remote_branches("https://github.com/org/repo.git")
                assert False, "Should have raised"
            except Exception as e:
                assert "repository not found" in str(e)
