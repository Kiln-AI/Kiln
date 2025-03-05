"""
# Adapters

Adapters are used to connect Kiln to external systems, or to add new functionality to Kiln.

Model adapters are used to call AI models, like Ollama, OpenAI, etc.

The ml_model_list submodule contains a list of models that can be used for machine learning tasks. More can easily be added, but we keep a list here of models that are known to work well with Kiln's structured data and tool calling systems.

The prompt_builders submodule contains classes that build prompts for use with the AI agents.

The repair submodule contains an adapter for the repair task.

The parser submodule contains parsers for the output of the AI models.

The eval submodule contains the code for evaluating the performance of a model.
"""

from . import (
    data_gen,
    eval,
    fine_tune,
    ml_model_list,
    model_adapters,
    prompt_builders,
    repair,
)

__all__ = [
    "model_adapters",
    "data_gen",
    "fine_tune",
    "ml_model_list",
    "prompt_builders",
    "repair",
    "eval",
]
