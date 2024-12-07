from unittest.mock import Mock, patch

import pytest

from kiln_ai.datamodel import Project
from kiln_ai.datamodel.registry import all_projects, project_from_id


@pytest.fixture
def mock_config():
    with patch("kiln_ai.datamodel.registry.Config") as mock:
        config_instance = Mock()
        mock.shared.return_value = config_instance
        yield config_instance


@pytest.fixture
def mock_project():
    def create_mock_project(project_id: str = "test-id"):
        project = Mock(spec=Project)
        project.id = project_id
        return project

    return create_mock_project


def test_all_projects_empty(mock_config):
    mock_config.projects = None
    assert all_projects() == []


def test_all_projects_success(mock_config, mock_project):
    mock_config.projects = ["path1", "path2"]

    project1 = mock_project("project1")
    project2 = mock_project("project2")

    with patch("kiln_ai.datamodel.Project.load_from_file") as mock_load:
        mock_load.side_effect = [project1, project2]

        result = all_projects()

        assert len(result) == 2
        assert result[0] == project1
        assert result[1] == project2
        mock_load.assert_any_call("path1")
        mock_load.assert_any_call("path2")


def test_all_projects_with_errors(mock_config, mock_project):
    mock_config.projects = ["path1", "path2", "path3"]

    project1 = mock_project("project1")
    project3 = mock_project("project3")

    with patch("kiln_ai.datamodel.Project.load_from_file") as mock_load:
        mock_load.side_effect = [project1, Exception("File not found"), project3]

        result = all_projects()

        assert len(result) == 2
        assert result[0] == project1
        assert result[1] == project3


def test_project_from_id_not_found(mock_config):
    mock_config.projects = None
    assert project_from_id("any-id") is None


def test_project_from_id_success(mock_config, mock_project):
    mock_config.projects = ["path1", "path2"]

    project1 = mock_project("project1")
    project2 = mock_project("project2")

    with patch("kiln_ai.datamodel.Project.load_from_file") as mock_load:
        mock_load.side_effect = [project1, project2]

        result = project_from_id("project2")

        assert result == project2


def test_project_from_id_with_errors(mock_config, mock_project):
    mock_config.projects = ["path1", "path2", "path3"]

    project1 = mock_project("project1")
    project3 = mock_project("target-id")

    with patch("kiln_ai.datamodel.Project.load_from_file") as mock_load:
        mock_load.side_effect = [project1, Exception("File not found"), project3]

        result = project_from_id("target-id")

        assert result == project3
