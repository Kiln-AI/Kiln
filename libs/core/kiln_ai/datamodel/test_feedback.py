import json

import pytest
from pydantic import ValidationError

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


@pytest.fixture
def task_and_run(tmp_path):
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
    return task, run


class TestFeedbackModel:
    def test_create_feedback(self):
        fb = Feedback(feedback="Great output!", source=FeedbackSource.run_page)
        assert fb.feedback == "Great output!"
        assert fb.source == FeedbackSource.run_page
        assert fb.id is not None
        assert fb.created_at is not None
        assert fb.created_by is not None

    def test_feedback_requires_nonempty_text(self):
        with pytest.raises(ValidationError):
            Feedback(feedback="", source=FeedbackSource.run_page)

    def test_feedback_source_values(self):
        assert FeedbackSource.run_page.value == "run-page"
        assert FeedbackSource.spec_feedback.value == "spec-feedback"

    def test_model_type(self):
        fb = Feedback(feedback="test", source=FeedbackSource.run_page)
        assert fb.model_type == "feedback"


class TestFeedbackPersistence:
    def test_save_and_load(self, task_and_run):
        _, run = task_and_run
        fb = Feedback(
            feedback="Needs improvement",
            source=FeedbackSource.spec_feedback,
            parent=run,
        )
        fb.save_to_file()

        assert fb.path is not None
        assert fb.path.exists()

        loaded = Feedback.load_from_file(fb.path)
        assert loaded.feedback == "Needs improvement"
        assert loaded.source == FeedbackSource.spec_feedback
        assert loaded.id == fb.id

    def test_multiple_feedback_on_same_run(self, task_and_run):
        _, run = task_and_run
        fb1 = Feedback(
            feedback="First feedback",
            source=FeedbackSource.run_page,
            parent=run,
        )
        fb1.save_to_file()

        fb2 = Feedback(
            feedback="Second feedback",
            source=FeedbackSource.spec_feedback,
            parent=run,
        )
        fb2.save_to_file()

        all_feedback = run.feedback(readonly=True)
        assert len(all_feedback) == 2
        feedback_texts = {f.feedback for f in all_feedback}
        assert feedback_texts == {"First feedback", "Second feedback"}

    def test_feedback_parent_is_task_run(self, task_and_run):
        _, run = task_and_run
        fb = Feedback(
            feedback="test",
            source=FeedbackSource.run_page,
            parent=run,
        )
        fb.save_to_file()
        assert Feedback.parent_type().__name__ == "TaskRun"
        assert Feedback.relationship_name() == "feedback"

    def test_serialization_roundtrip(self, task_and_run):
        _, run = task_and_run
        fb = Feedback(
            feedback="Roundtrip test",
            source=FeedbackSource.run_page,
            parent=run,
        )
        fb.save_to_file()

        with open(fb.path) as f:
            data = json.load(f)
        assert data["feedback"] == "Roundtrip test"
        assert data["source"] == "run-page"
        assert "id" in data
        assert "created_at" in data
        assert "created_by" in data
