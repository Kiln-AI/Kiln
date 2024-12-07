"""
# Adapters

Adapters are used to connect Kiln to external systems, or to add new functionality to Kiln.

BaseAdapter is extensible, and used for adding adapters that provide AI functionality. There's currently a LangChain adapter which provides a bridge to LangChain.

The ml_model_list submodule contains a list of models that can be used for machine learning tasks. More can easily be added, but we keep a list here of models that are known to work well with Kiln's structured data and tool calling systems.

The prompt_builders submodule contains classes that build prompts for use with the AI agents.

The repair submodule contains an adapter for the repair task.
"""

from . import (
    base_adapter,
    data_gen,
    fine_tune,
    langchain_adapters,
    ml_model_list,
    prompt_builders,
    repair,
)

__all__ = [
    "base_adapter",
    "langchain_adapters",
    "ml_model_list",
    "prompt_builders",
    "repair",
    "data_gen",
    "fine_tune",
]
