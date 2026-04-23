import pytest

from kiln_ai.datamodel.prompt_type import prompt_type_label


@pytest.mark.parametrize(
    "prompt_id,generator_id,expected",
    [
        ("fine_tune_prompt::abc123", None, "Fine-Tune"),
        ("fine_tune_prompt::xyz", "kiln_prompt_optimizer", "Fine-Tune"),
        ("task_run_config::p::t::rc", None, "Frozen"),
        ("task_run_config::p::t::rc", "few_shot_prompt_builder", "Frozen"),
        ("id::abc", "kiln_prompt_optimizer", "Kiln Optimized"),
        ("id::abc", "few_shot_prompt_builder", "Few-Shot"),
        ("id::abc", "multi_shot_prompt_builder", "Many-Shot"),
        ("id::abc", "repairs_prompt_builder", "Repair Multi-Shot"),
        (
            "id::abc",
            "simple_chain_of_thought_prompt_builder",
            "Chain of Thought",
        ),
        (
            "id::abc",
            "few_shot_chain_of_thought_prompt_builder",
            "Chain of Thought + Few Shot",
        ),
        (
            "id::abc",
            "multi_shot_chain_of_thought_prompt_builder",
            "Chain of Thought + Many Shot",
        ),
        ("id::abc", None, "Custom"),
        ("id::abc", "unknown_generator", "Custom"),
        ("something_else", None, "Unknown"),
        ("something_else", "unknown_generator", "Unknown"),
    ],
)
def test_prompt_type_label(
    prompt_id: str, generator_id: str | None, expected: str
) -> None:
    assert prompt_type_label(prompt_id, generator_id) == expected
