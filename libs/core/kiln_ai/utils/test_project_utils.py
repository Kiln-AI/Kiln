from unittest.mock import patch

import pytest

from kiln_ai.datamodel import Project
from kiln_ai.utils.project_utils import (
    DuplicateProjectError,
    check_duplicate_project_id,
    project_from_id,
)


class TestProjectFromId:
    def test_returns_matching_project(self):
        project = Project(name="Test", description="desc", id="proj-1")
        with (
            patch("kiln_ai.utils.project_utils.Config.shared") as mock_config,
            patch(
                "kiln_ai.utils.project_utils.Project.load_from_file",
                return_value=project,
            ),
        ):
            mock_config.return_value.projects = ["/path/project.kiln"]
            result = project_from_id("proj-1")
        assert result is not None
        assert result.id == "proj-1"

    def test_returns_none_when_no_match(self):
        project = Project(name="Test", description="desc", id="proj-1")
        with (
            patch("kiln_ai.utils.project_utils.Config.shared") as mock_config,
            patch(
                "kiln_ai.utils.project_utils.Project.load_from_file",
                return_value=project,
            ),
        ):
            mock_config.return_value.projects = ["/path/project.kiln"]
            result = project_from_id("nonexistent")
        assert result is None

    def test_returns_none_when_no_projects(self):
        with patch("kiln_ai.utils.project_utils.Config.shared") as mock_config:
            mock_config.return_value.projects = None
            result = project_from_id("any-id")
        assert result is None

    def test_skips_load_errors(self):
        with (
            patch("kiln_ai.utils.project_utils.Config.shared") as mock_config,
            patch(
                "kiln_ai.utils.project_utils.Project.load_from_file",
                side_effect=Exception("file not found"),
            ),
        ):
            mock_config.return_value.projects = ["/path/project.kiln"]
            result = project_from_id("any-id")
        assert result is None


class TestCheckDuplicateProjectId:
    def test_no_projects_configured(self):
        with patch("kiln_ai.utils.project_utils.Config.shared") as mock_config:
            mock_config.return_value.projects = None
            check_duplicate_project_id("proj-1", "/path/project.kiln")

    def test_no_duplicate(self):
        project = Project(name="Existing", description="desc", id="proj-2")
        with (
            patch("kiln_ai.utils.project_utils.Config.shared") as mock_config,
            patch(
                "kiln_ai.utils.project_utils.Project.load_from_file",
                return_value=project,
            ),
        ):
            mock_config.return_value.projects = ["/path/project.kiln"]
            check_duplicate_project_id("proj-1", "/new/project.kiln")

    def test_same_id_same_path(self, tmp_path):
        project_file = tmp_path / "project.kiln"
        project_file.touch()
        project = Project(name="Existing", description="desc", id="proj-1")
        with (
            patch("kiln_ai.utils.project_utils.Config.shared") as mock_config,
            patch(
                "kiln_ai.utils.project_utils.Project.load_from_file",
                return_value=project,
            ),
        ):
            mock_config.return_value.projects = [str(project_file)]
            with pytest.raises(DuplicateProjectError) as exc_info:
                check_duplicate_project_id("proj-1", str(project_file))
            assert exc_info.value.same_path is True
            assert "already imported" in str(exc_info.value)

    def test_same_id_different_path(self):
        project = Project(name="My Project", description="desc", id="proj-1")
        with (
            patch("kiln_ai.utils.project_utils.Config.shared") as mock_config,
            patch(
                "kiln_ai.utils.project_utils.Project.load_from_file",
                return_value=project,
            ),
        ):
            mock_config.return_value.projects = ["/existing/project.kiln"]
            with pytest.raises(DuplicateProjectError) as exc_info:
                check_duplicate_project_id("proj-1", "/different/project.kiln")
            assert exc_info.value.same_path is False
            assert 'remove project "My Project"' in str(exc_info.value)

    def test_skips_unloadable_projects(self):
        with (
            patch("kiln_ai.utils.project_utils.Config.shared") as mock_config,
            patch(
                "kiln_ai.utils.project_utils.Project.load_from_file",
                side_effect=Exception("corrupt file"),
            ),
        ):
            mock_config.return_value.projects = ["/corrupt/project.kiln"]
            check_duplicate_project_id("proj-1", "/new/project.kiln")

    def test_empty_projects_list(self):
        with patch("kiln_ai.utils.project_utils.Config.shared") as mock_config:
            mock_config.return_value.projects = []
            check_duplicate_project_id("proj-1", "/path/project.kiln")
