from unittest.mock import AsyncMock, Mock, patch

import pytest
from app.desktop.studio_server.judge_job_api import connect_judge_job_api
from fastapi import FastAPI
from fastapi.testclient import TestClient
from kiln_server.custom_errors import connect_custom_errors

from kiln_ai.adapters.eval.judge_job_runner import JudgeJobItemError, JudgeJobRunResult
from kiln_ai.datamodel import (
    JudgeJob,
    JudgeJobRun,
    Project,
    Task,
    TaskOutputRatingType,
)
from kiln_ai.datamodel.eval import Eval, EvalConfig, EvalConfigType, EvalOutputScore

BASE = "/api/projects/project1/tasks/task1/judge_jobs"


@pytest.fixture
def app():
    app = FastAPI()
    connect_custom_errors(app)
    connect_judge_job_api(app)
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def mock_task(tmp_path):
    project = Project(id="project1", name="P", path=tmp_path / "project.kiln")
    project.save_to_file()
    task = Task(
        id="task1",
        name="T",
        instruction="do",
        path=tmp_path / "task.kiln",
        parent=project,
    )
    task.save_to_file()
    return task


@pytest.fixture
def mock_eval_config(mock_task):
    eval = Eval(
        id="eval1",
        name="e",
        eval_set_filter_id="all",
        eval_configs_filter_id="all",
        output_scores=[
            EvalOutputScore(name="Accuracy", type=TaskOutputRatingType.pass_fail)
        ],
        parent=mock_task,
    )
    eval.save_to_file()
    eval_config = EvalConfig(
        id="eval_config1",
        name="c",
        model_name="gpt-4",
        model_provider="openai",
        config_type=EvalConfigType.g_eval,
        properties={"eval_steps": ["s"]},
        parent=eval,
    )
    eval_config.save_to_file()
    return eval_config


@pytest.fixture
def mock_task_from_id(mock_task):
    with patch("app.desktop.studio_server.judge_job_api.task_from_id") as m:
        m.return_value = mock_task
        yield m


@pytest.fixture
def saved_job(mock_task, mock_eval_config):
    job = JudgeJob(
        id="jj1",
        name="scan",
        target_tags=["train"],
        eval_config_id=mock_eval_config.id,
        parent=mock_task,
    )
    job.save_to_file()
    return job


def patched_runner(result: JudgeJobRunResult):
    """Patch JudgeJobRunner so the endpoint returns `result` without real judging."""
    runner = Mock()
    runner.run = AsyncMock(return_value=result)
    mock_cls = patch(
        "app.desktop.studio_server.judge_job_api.JudgeJobRunner", return_value=runner
    )
    return mock_cls


def test_create_judge_job(client, mock_task, mock_task_from_id, mock_eval_config):
    resp = client.post(
        BASE,
        json={
            "name": "scan",
            "target_tags": ["train"],
            "eval_config_id": "eval_config1",
            "count": 3,
            "max_samples": 10,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "scan"
    assert body["target_tags"] == ["train"]
    assert body["count"] == 3
    assert len(mock_task.judge_jobs()) == 1


def test_create_generates_name(client, mock_task, mock_task_from_id, mock_eval_config):
    resp = client.post(
        BASE, json={"target_tags": ["train"], "eval_config_id": "eval_config1"}
    )
    assert resp.status_code == 200
    assert resp.json()["name"]


def test_create_unknown_eval_config(
    client, mock_task, mock_task_from_id, mock_eval_config
):
    resp = client.post(BASE, json={"target_tags": ["train"], "eval_config_id": "nope"})
    assert resp.status_code == 404


def test_create_unknown_run_config(
    client, mock_task, mock_task_from_id, mock_eval_config
):
    resp = client.post(
        BASE,
        json={
            "target_tags": ["train"],
            "eval_config_id": "eval_config1",
            "run_config_id": "nope",
        },
    )
    assert resp.status_code == 404


def test_create_validation(client, mock_task, mock_task_from_id, mock_eval_config):
    bad_counts = client.post(
        BASE,
        json={
            "target_tags": ["train"],
            "eval_config_id": "eval_config1",
            "count": 5,
            "max_samples": 2,
        },
    )
    assert bad_counts.status_code == 422

    empty_tags = client.post(
        BASE, json={"target_tags": [], "eval_config_id": "eval_config1"}
    )
    assert empty_tags.status_code == 422


def test_run_judge_job(
    client, mock_task, mock_task_from_id, mock_eval_config, saved_job
):
    result = JudgeJobRunResult(
        failing_runs=[
            JudgeJobRun(
                parent=saved_job,
                task_run_id="d1",
                scores={"accuracy": 0.0},
                feedback="bad",
                passed=False,
            )
        ],
        num_judged=3,
        failing_count=1,
        train_set_size=10,
        hit_cap=False,
        errors=[JudgeJobItemError(task_run_id="d2", error="Error judging item: boom")],
    )
    with patched_runner(result):
        resp = client.post(f"{BASE}/jj1/run")

    assert resp.status_code == 200
    body = resp.json()
    assert body["judge_job"]["id"] == "jj1"
    assert body["num_judged"] == 3
    assert body["failing_count"] == 1
    assert body["train_set_size"] == 10
    assert body["hit_cap"] is False
    assert len(body["failing_runs"]) == 1
    assert body["failing_runs"][0]["task_run_id"] == "d1"
    assert body["failing_runs"][0]["feedback"] == "bad"
    # Per-item errors are surfaced so the caller can see partial failures.
    assert body["errors"] == [
        {"task_run_id": "d2", "error": "Error judging item: boom"}
    ]


def test_run_judge_job_404(client, mock_task, mock_task_from_id, mock_eval_config):
    resp = client.post(f"{BASE}/nope/run")
    assert resp.status_code == 404


def test_create_and_run(client, mock_task, mock_task_from_id, mock_eval_config):
    result = JudgeJobRunResult(
        failing_runs=[],
        num_judged=0,
        failing_count=0,
        train_set_size=0,
        hit_cap=False,
    )
    with patched_runner(result):
        resp = client.post(
            f"{BASE}/run",
            json={"target_tags": ["train"], "eval_config_id": "eval_config1"},
        )

    assert resp.status_code == 200
    assert resp.json()["judge_job"]["target_tags"] == ["train"]
    # the job was created/persisted
    assert len(mock_task.judge_jobs()) == 1


def test_get_judge_job(client, mock_task, mock_task_from_id, saved_job):
    resp = client.get(f"{BASE}/jj1")
    assert resp.status_code == 200
    assert resp.json()["id"] == "jj1"


def test_get_judge_job_404(client, mock_task, mock_task_from_id):
    resp = client.get(f"{BASE}/nope")
    assert resp.status_code == 404


def test_get_judge_job_runs(client, mock_task, mock_task_from_id, saved_job):
    JudgeJobRun(
        parent=saved_job,
        task_run_id="d1",
        scores={"accuracy": 0.0},
        feedback="bad",
        passed=False,
    ).save_to_file()
    JudgeJobRun(
        parent=saved_job, task_run_id="d2", scores={"accuracy": 1.0}, passed=True
    ).save_to_file()

    resp = client.get(f"{BASE}/jj1/runs")
    assert resp.status_code == 200
    assert len(resp.json()) == 2

    failing = client.get(f"{BASE}/jj1/runs", params={"failing_only": True})
    assert failing.status_code == 200
    body = failing.json()
    assert len(body) == 1
    assert body[0]["task_run_id"] == "d1"
    assert body[0]["feedback"] == "bad"


def test_list_judge_jobs(client, mock_task, mock_task_from_id, saved_job):
    resp = client.get(BASE)
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["id"] == "jj1"
