from unittest.mock import patch

import pytest
from fastapi import HTTPException
from kiln_ai.datamodel import Project, Prompt, Task
from kiln_ai.datamodel.datamodel_enums import ModelProviderName, StructuredOutputMode
from kiln_ai.datamodel.provenance import KilnArtifactProvenance
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties
from kiln_ai.datamodel.task import TaskRunConfig

from kiln_server.provenance_api import validate_provenance_or_400


@pytest.fixture
def task_with_prompts(tmp_path):
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()
    task = Task(name="Test Task", instruction="Do the thing.", parent=project)
    task.save_to_file()
    prompts = [Prompt(name=f"Prompt {i}", prompt="text", parent=task) for i in range(3)]
    for prompt in prompts:
        prompt.save_to_file()
    return task, prompts


def provenance(ids: list[str]) -> KilnArtifactProvenance:
    return KilnArtifactProvenance.model_validate(
        {"origin": "human", "derived_from_ids": ids}
    )


def test_known_siblings_pass(task_with_prompts):
    task, prompts = task_with_prompts
    ids = [str(p.id) for p in prompts]
    validate_provenance_or_400(provenance(ids), "new-id", Prompt, task.path)


@pytest.mark.parametrize(
    "ids,unknown",
    [
        (["missing"], "missing"),
        (["{0}", "missing", "other-missing"], "missing"),
        (["other-missing", "{0}", "missing"], "other-missing"),
    ],
)
def test_first_unknown_sibling_is_named_in_400(task_with_prompts, ids, unknown):
    task, prompts = task_with_prompts
    ids = [i.format(prompts[0].id) for i in ids]
    with pytest.raises(HTTPException) as exc:
        validate_provenance_or_400(provenance(ids), "new-id", Prompt, task.path)
    assert exc.value.status_code == 400
    assert exc.value.detail == f"derived_from_ids references unknown sibling: {unknown}"


def test_existing_id_of_another_type_in_the_same_scope_is_400(task_with_prompts):
    task, _ = task_with_prompts
    run_config = TaskRunConfig(
        name="Run Config",
        parent=task,
        run_config_properties=KilnAgentRunConfigProperties(
            model_name="gpt-4o",
            model_provider_name=ModelProviderName.openai,
            prompt_id="simple_prompt_builder",
            structured_output_mode=StructuredOutputMode.json_schema,
        ),
    )
    run_config.save_to_file()
    with pytest.raises(HTTPException) as exc:
        validate_provenance_or_400(
            provenance([str(run_config.id)]), "new-id", Prompt, task.path
        )
    assert exc.value.status_code == 400
    assert "unknown sibling" in exc.value.detail


def test_existing_id_of_the_same_type_in_another_scope_is_400(task_with_prompts):
    task, _ = task_with_prompts
    other_task = Task(name="Other Task", instruction="Other.", parent=task.parent)
    other_task.save_to_file()
    other_prompt = Prompt(name="Other Prompt", prompt="text", parent=other_task)
    other_prompt.save_to_file()
    with pytest.raises(HTTPException) as exc:
        validate_provenance_or_400(
            provenance([str(other_prompt.id)]), "new-id", Prompt, task.path
        )
    assert exc.value.status_code == 400
    assert "unknown sibling" in exc.value.detail


def test_self_reference_is_400(task_with_prompts):
    task, prompts = task_with_prompts
    self_id = str(prompts[0].id)
    with pytest.raises(HTTPException) as exc:
        validate_provenance_or_400(provenance([self_id]), self_id, Prompt, task.path)
    assert exc.value.status_code == 400
    assert "cannot reference this artifact itself" in exc.value.detail


def test_all_ids_resolve_in_one_bulk_lookup(task_with_prompts):
    task, prompts = task_with_prompts
    ids = [str(p.id) for p in prompts]
    with (
        patch.object(
            Prompt, "from_ids_and_parent_path", wraps=Prompt.from_ids_and_parent_path
        ) as bulk_lookup,
        patch.object(Prompt, "from_id_and_parent_path") as single_lookup,
    ):
        validate_provenance_or_400(provenance(ids), "new-id", Prompt, task.path)
    bulk_lookup.assert_called_once_with(set(ids), task.path, readonly=True)
    single_lookup.assert_not_called()


@pytest.mark.parametrize("value", [None, KilnArtifactProvenance(origin="agent")])
def test_no_lineage_skips_the_lookup(task_with_prompts, value):
    task, _ = task_with_prompts
    with patch.object(Prompt, "from_ids_and_parent_path") as bulk_lookup:
        validate_provenance_or_400(value, "new-id", Prompt, task.path)
    bulk_lookup.assert_not_called()
