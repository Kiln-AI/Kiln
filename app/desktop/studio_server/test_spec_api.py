from unittest.mock import patch

import pytest
from app.desktop.studio_server.api_client.kiln_ai_server_client.models import (
    ExampleWithFeedback,
    RefineSpecOutput,
    RefineSpecOutputNewProposedSpecEdits,
    SpecEdit,
    SpecInfo,
    SpecInfoSpecFieldCurrentValues,
    SpecInfoSpecFields,
    SubsampleBatchOutput,
    SubsampleBatchOutputItem,
    TaskInfo,
)
from app.desktop.studio_server.spec_api import connect_spec_api
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    app = FastAPI()
    connect_spec_api(app)
    return TestClient(app)


@pytest.fixture
def mock_clarify_response():
    return SubsampleBatchOutput(
        examples_for_feedback=[
            SubsampleBatchOutputItem(
                input_="test input",
                output="test output",
                exhibits_issue=True,
            )
        ]
    )


@pytest.fixture
def mock_refine_response():
    new_proposed_spec_edits = RefineSpecOutputNewProposedSpecEdits()
    new_proposed_spec_edits["name"] = SpecEdit(
        old_value="Old name",
        proposed_edit="Updated name",
        reason_for_edit="Needs to be more specific",
    )
    new_proposed_spec_edits["description"] = SpecEdit(
        old_value="Old description",
        proposed_edit="Updated description",
        reason_for_edit="More clarity needed",
    )

    return RefineSpecOutput(
        new_proposed_spec_edits=new_proposed_spec_edits,
        out_of_scope_feedback="Some feedback",
    )


@pytest.fixture
def mock_clarify_api():
    with patch(
        "app.desktop.studio_server.spec_api.clarify_spec_api_dev_clarify_spec_post.asyncio"
    ) as mock:
        yield mock


@pytest.fixture
def mock_refine_api():
    with patch(
        "app.desktop.studio_server.spec_api.refine_spec_api_dev_refine_spec_post.asyncio"
    ) as mock:
        yield mock


def test_clarify_spec_success(client, mock_clarify_api, mock_clarify_response):
    mock_clarify_api.return_value = mock_clarify_response

    response = client.post(
        "/api/spec/clarify",
        json={
            "task_prompt_with_few_shot": "Generate a joke",
            "task_input_schema": "",
            "task_output_schema": "",
            "spec_rendered_prompt_template": "Test template",
            "num_samples_per_topic": 10,
            "num_topics": 10,
            "num_exemplars": 10,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert "examples_for_feedback" in data
    assert len(data["examples_for_feedback"]) == 1
    assert data["examples_for_feedback"][0]["input"] == "test input"
    assert data["examples_for_feedback"][0]["output"] == "test output"
    assert data["examples_for_feedback"][0]["exhibits_issue"] is True


def test_clarify_spec_default_num_exemplars(
    client, mock_clarify_api, mock_clarify_response
):
    mock_clarify_api.return_value = mock_clarify_response

    response = client.post(
        "/api/spec/clarify",
        json={
            "task_prompt_with_few_shot": "Generate a joke",
            "task_input_schema": "",
            "task_output_schema": "",
            "spec_rendered_prompt_template": "Test template",
            "num_samples_per_topic": 10,
            "num_topics": 10,
        },
    )

    assert response.status_code == 200


def test_clarify_spec_none_response(client, mock_clarify_api):
    mock_clarify_api.return_value = None

    response = client.post(
        "/api/spec/clarify",
        json={
            "task_prompt_with_few_shot": "Generate a joke",
            "task_input_schema": "",
            "task_output_schema": "",
            "spec_rendered_prompt_template": "Test template",
            "num_samples_per_topic": 10,
            "num_topics": 10,
        },
    )

    assert response.status_code == 500
    assert "No response" in response.text


def test_refine_spec_success(client, mock_refine_api, mock_refine_response):
    mock_refine_api.return_value = mock_refine_response

    spec_fields = SpecInfoSpecFields()
    spec_fields["name"] = "Give your issue eval a short name"
    spec_fields["description"] = "Describe the issue you're trying to catch"

    spec_field_values = SpecInfoSpecFieldCurrentValues()
    spec_field_values["name"] = "No Punctuation in Titles"
    spec_field_values["description"] = "The model should not use any punctuation"

    spec_info = SpecInfo(
        spec_fields=spec_fields,
        spec_field_current_values=spec_field_values,
    )

    task_info = TaskInfo(
        task_prompt="You create titles for photo albums",
        few_shot_examples="Input: photo captions\nOutput: A title",
    )

    example_feedback = ExampleWithFeedback(
        user_rating_exhibits_issue_correct=False,
        user_feedback="Actually this is fine",
        input_="a photo of family gathering",
        output="Family get-together",
        exhibits_issue=True,
    )

    response = client.post(
        "/api/spec/refine",
        json={
            "task_prompt_with_few_shot": "You create titles for photo albums...",
            "task_input_schema": "A list of photo captions",
            "task_output_schema": "A photo album title",
            "task_info": task_info.to_dict(),
            "spec": spec_info.to_dict(),
            "examples_with_feedback": [example_feedback.to_dict()],
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert "new_proposed_spec_edits" in data
    assert "out_of_scope_feedback" in data
    assert data["out_of_scope_feedback"] == "Some feedback"


def test_refine_spec_none_response(client, mock_refine_api):
    mock_refine_api.return_value = None

    spec_fields = SpecInfoSpecFields()
    spec_field_values = SpecInfoSpecFieldCurrentValues()
    spec_info = SpecInfo(
        spec_fields=spec_fields,
        spec_field_current_values=spec_field_values,
    )
    task_info = TaskInfo(task_prompt="Test prompt")

    response = client.post(
        "/api/spec/refine",
        json={
            "task_prompt_with_few_shot": "Test",
            "task_input_schema": "",
            "task_output_schema": "",
            "task_info": task_info.to_dict(),
            "spec": spec_info.to_dict(),
            "examples_with_feedback": [],
        },
    )

    assert response.status_code == 500
    assert "No response" in response.text


def test_generate_batch_success(client, mock_clarify_api, mock_clarify_response):
    mock_clarify_api.return_value = mock_clarify_response

    response = client.post(
        "/api/spec/generate_batch",
        json={
            "task_prompt_with_few_shot": "Generate a joke",
            "task_input_schema": "",
            "task_output_schema": "",
            "spec_rendered_prompt_template": "Test template",
            "num_samples_per_topic": 10,
            "num_topics": 10,
            "enable_scoring": False,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert "examples_for_feedback" in data
    assert len(data["examples_for_feedback"]) == 1


def test_generate_batch_with_scoring(client, mock_clarify_api, mock_clarify_response):
    mock_clarify_api.return_value = mock_clarify_response

    response = client.post(
        "/api/spec/generate_batch",
        json={
            "task_prompt_with_few_shot": "Generate a joke",
            "task_input_schema": "",
            "task_output_schema": "",
            "spec_rendered_prompt_template": "Test template",
            "num_samples_per_topic": 10,
            "num_topics": 10,
            "enable_scoring": True,
        },
    )

    assert response.status_code == 200


def test_generate_batch_none_response(client, mock_clarify_api):
    mock_clarify_api.return_value = None

    response = client.post(
        "/api/spec/generate_batch",
        json={
            "task_prompt_with_few_shot": "Generate a joke",
            "task_input_schema": "",
            "task_output_schema": "",
            "spec_rendered_prompt_template": "Test template",
            "num_samples_per_topic": 10,
            "num_topics": 10,
            "enable_scoring": False,
        },
    )

    assert response.status_code == 500
    assert "No response" in response.text
