# TODO (merge blocker — do not merge toward main until resolved): tests for a datamodel under
# design review — see the header of kiln_ai/datamodel/judge_feedback_batch.py. Resolve before
# merging toward main.

import pytest

from kiln_ai.datamodel import JudgeFeedbackBatch, JudgeFeedbackBatchRun, Project, Task


@pytest.fixture
def task(tmp_path):
    project = Project(name="P", path=tmp_path / "project.kiln")
    project.save_to_file()
    task = Task(name="T", instruction="do", path=tmp_path / "task.kiln", parent=project)
    task.save_to_file()
    return task


def test_defaults(task):
    job = JudgeFeedbackBatch(
        name="scan", target_tags=["train"], eval_config_id="ec1", parent=task
    )
    assert job.stop_after_failures is None
    assert job.max_samples == 50
    assert job.threshold == 0.75
    assert job.run_config_id is None


def test_parent_task_typing(task):
    job = JudgeFeedbackBatch(
        name="scan", target_tags=["t"], eval_config_id="ec1", parent=task
    )
    assert job.parent_task().id == task.id


def test_create_and_roundtrip(task):
    job = JudgeFeedbackBatch(
        name="scan",
        target_tags=["train"],
        eval_config_id="ec1",
        run_config_id="rc1",
        stop_after_failures=3,
        max_samples=20,
        threshold=0.5,
        parent=task,
    )
    job.save_to_file()
    JudgeFeedbackBatchRun(
        parent=job,
        task_run_id="d1",
        scores={"accuracy": 0.0},
        feedback="bad",
        passed=False,
    ).save_to_file()
    JudgeFeedbackBatchRun(
        parent=job,
        task_run_id="d2",
        scores={"accuracy": 1.0},
        feedback=None,
        passed=True,
    ).save_to_file()

    # Reload through the Task accessor
    jobs = task.judge_feedback_batches()
    assert len(jobs) == 1
    reloaded = jobs[0]
    assert reloaded.name == "scan"
    assert reloaded.target_tags == ["train"]
    assert reloaded.eval_config_id == "ec1"
    assert reloaded.run_config_id == "rc1"
    assert reloaded.stop_after_failures == 3
    assert reloaded.threshold == 0.5

    runs = reloaded.runs()
    assert len(runs) == 2
    failing = [r for r in runs if not r.passed]
    assert len(failing) == 1
    assert failing[0].task_run_id == "d1"
    assert failing[0].feedback == "bad"
    assert failing[0].scores == {"accuracy": 0.0}


def test_run_parent_typing(task):
    job = JudgeFeedbackBatch(
        name="scan", target_tags=["t"], eval_config_id="ec1", parent=task
    )
    job.save_to_file()
    run = JudgeFeedbackBatchRun(
        parent=job, task_run_id="d1", scores={"accuracy": 1.0}, passed=True
    )
    assert run.parent_judge_feedback_batch().id == job.id


def test_generate_outputs_requires_run_config_id(task):
    with pytest.raises(ValueError, match="run_config_id is required"):
        JudgeFeedbackBatch(
            name="scan",
            target_tags=["t"],
            eval_config_id="ec1",
            generate_outputs=True,
            parent=task,
        )
    # generate_outputs=True with a run_config_id is valid.
    job = JudgeFeedbackBatch(
        name="scan",
        target_tags=["t"],
        eval_config_id="ec1",
        generate_outputs=True,
        run_config_id="rc1",
        parent=task,
    )
    assert job.generate_outputs is True


def test_empty_target_tags_rejected(task):
    with pytest.raises(ValueError, match="at least one tag"):
        JudgeFeedbackBatch(
            name="scan", target_tags=[], eval_config_id="ec1", parent=task
        )
