"""
# Adapters

Adapters are used to connect Kiln to external systems, or to add new functionality to Kiln.

Model adapters are used to call AI models, like Ollama, OpenAI, etc.

The ml_model_list submodule contains a list of models that can be used for machine learning tasks. More can easily be added, but we keep a list here of models that are known to work well with Kiln's structured data and tool calling systems.

The prompt_builders submodule contains classes that build prompts for use with the AI agents.

The repair submodule contains an adapter for the repair task.

The parser submodule contains parsers for the output of the AI models.

The eval submodule contains the code for evaluating the performance of a model.

Note: Some submodules are not imported here to avoid loading optional dependencies.
- chunkers: Requires 'rag' optional dependencies (pip install kiln-ai[rag])
- fine_tune: Some providers require optional dependencies
"""

from . import (
    chat,
    data_gen,
    eval,
    extractors,
    ml_embedding_model_list,
    ml_model_list,
    model_adapters,
    prompt_builders,
    repair,
)

__all__ = [
    "chat",
    "data_gen",
    "eval",
    "extractors",
    "ml_embedding_model_list",
    "ml_model_list",
    "model_adapters",
    "prompt_builders",
    "repair",
]
