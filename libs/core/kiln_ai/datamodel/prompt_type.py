_GENERATOR_LABELS: dict[str, str] = {
    "simple_prompt_builder": "Basic (Zero Shot)",
    "kiln_prompt_optimizer": "Kiln Optimized",
    "few_shot_prompt_builder": "Few-Shot",
    "multi_shot_prompt_builder": "Many-Shot",
    "repairs_prompt_builder": "Repair Multi-Shot",
    "simple_chain_of_thought_prompt_builder": "Chain of Thought",
    "few_shot_chain_of_thought_prompt_builder": "Chain of Thought + Few Shot",
    "multi_shot_chain_of_thought_prompt_builder": "Chain of Thought + Many Shot",
}


def prompt_type_label(prompt_id: str, generator_id: str | None) -> str:
    """Derive a human-readable type label for a prompt.

    Port of the TS `getPromptType` in prompt_generators.ts.
    """
    if prompt_id.startswith("fine_tune_prompt::"):
        return "Fine-Tune"
    if prompt_id.startswith("task_run_config::"):
        return "Frozen"
    if generator_id:
        label = _GENERATOR_LABELS.get(generator_id)
        if label:
            return label
    if prompt_id.startswith("id::"):
        return "Custom"
    return "Unknown"
