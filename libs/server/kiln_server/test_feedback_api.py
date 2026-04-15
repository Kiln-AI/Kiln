from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from kiln_ai.datamodel import (
    DataSource,
    DataSourceType,
    Feedback,
    FeedbackSource,
    Project,
    Task,
    TaskOutput,
    TaskRun,
)

from kiln_server.custom_errors import connect_custom_errors
from kiln_server.feedback_api import connect_feedback_api


@pytest.fixture
def app():
    app = FastAPI()
    connect_feedback_api(app)
    connect_custom_errors(app)
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def task_run_setup(tmp_path):
    project = Project(
        name="Test Project", path=tmp_path / "test_project" / "project.kiln"
    )
    project.save_to_file()
    task = Task(
        name="Test Task",
        instruction="Do something",
        parent=project,
    )
    task.save_to_file()
    run = TaskRun(
        parent=task,
        input="Test input",
        input_source=DataSource(
            type=DataSourceType.human, properties={"created_by": "tester"}
        ),
        output=TaskOutput(
            output="Test output",
            source=DataSource(
                type=DataSourceType.synthetic,
                properties={
                    "model_name": "test_model",
                    "model_provider": "openai",
                    "adapter_name": "test_adapter",
                    "prompt_id": "simple_prompt_builder",
                },
            ),
        ),
    )
    run.save_to_file()
    return project, task, run


class TestListFeedback:
    def test_list_empty(self, client, task_run_setup):
        project, task, run = task_run_setup
        with patch("kiln_server.feedback_api.task_from_id", return_value=task):
            resp = client.get(
                f"/api/projects/{project.id}/tasks/{task.id}/runs/{run.id}/feedback"
            )
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_returns_feedback(self, client, task_run_setup):
        project, task, run = task_run_setup
        fb = Feedback(
            feedback="Test feedback", source=FeedbackSource.run_page, parent=run
        )
        fb.save_to_file()

        with patch("kiln_server.feedback_api.task_from_id", return_value=task):
            resp = client.get(
                f"/api/projects/{project.id}/tasks/{task.id}/runs/{run.id}/feedback"
            )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["feedback"] == "Test feedback"
        assert data[0]["source"] == "run-page"

    def test_list_run_not_found(self, client, task_run_setup):
        _, task, _ = task_run_setup
        with patch("kiln_server.feedback_api.task_from_id", return_value=task):
            resp = client.get(
                f"/api/projects/p/tasks/{task.id}/runs/nonexistent/feedback"
            )
        assert resp.status_code == 404


class TestCreateFeedback:
    def test_create(self, client, task_run_setup):
        project, task, run = task_run_setup
        with patch("kiln_server.feedback_api.task_from_id", return_value=task):
            resp = client.post(
                f"/api/projects/{project.id}/tasks/{task.id}/runs/{run.id}/feedback",
                json={"feedback": "Looks good", "source": "run-page"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["feedback"] == "Looks good"
        assert data["source"] == "run-page"
        assert "id" in data
        assert "created_at" in data

    def test_create_persists_to_disk(self, client, task_run_setup):
        project, task, run = task_run_setup
        with patch("kiln_server.feedback_api.task_from_id", return_value=task):
            resp = client.post(
                f"/api/projects/{project.id}/tasks/{task.id}/runs/{run.id}/feedback",
                json={"feedback": "Persisted", "source": "spec-feedback"},
            )
        assert resp.status_code == 200

        feedback_list = run.feedback(readonly=True)
        assert len(feedback_list) == 1
        assert feedback_list[0].feedback == "Persisted"

    def test_create_empty_feedback_rejected(self, client, task_run_setup):
        project, task, run = task_run_setup
        with patch("kiln_server.feedback_api.task_from_id", return_value=task):
            resp = client.post(
                f"/api/projects/{project.id}/tasks/{task.id}/runs/{run.id}/feedback",
                json={"feedback": "", "source": "run-page"},
            )
        assert resp.status_code == 422

    def test_create_run_not_found(self, client, task_run_setup):
        _, task, _ = task_run_setup
        with patch("kiln_server.feedback_api.task_from_id", return_value=task):
            resp = client.post(
                f"/api/projects/p/tasks/{task.id}/runs/nonexistent/feedback",
                json={"feedback": "test", "source": "run-page"},
            )
        assert resp.status_code == 404


class TestDeleteFeedback:
    def test_delete(self, client, task_run_setup):
        project, task, run = task_run_setup
        fb = Feedback(
            feedback="To be deleted", source=FeedbackSource.run_page, parent=run
        )
        fb.save_to_file()
        assert len(run.feedback(readonly=True)) == 1

        with patch("kiln_server.feedback_api.task_from_id", return_value=task):
            resp = client.delete(
                f"/api/projects/{project.id}/tasks/{task.id}/runs/{run.id}/feedback/{fb.id}"
            )
        assert resp.status_code == 200
        assert len(run.feedback(readonly=True)) == 0

    def test_delete_feedback_not_found(self, client, task_run_setup):
        project, task, run = task_run_setup
        with patch("kiln_server.feedback_api.task_from_id", return_value=task):
            resp = client.delete(
                f"/api/projects/{project.id}/tasks/{task.id}/runs/{run.id}/feedback/nonexistent"
            )
        assert resp.status_code == 404

    def test_delete_run_not_found(self, client, task_run_setup):
        _, task, _ = task_run_setup
        with patch("kiln_server.feedback_api.task_from_id", return_value=task):
            resp = client.delete(
                f"/api/projects/p/tasks/{task.id}/runs/nonexistent/feedback/someid"
            )
        assert resp.status_code == 404
