"""
# Adapters

Adapters are used to connect Kiln to external systems, or to add new functionality to Kiln.

Model adapters are used to call AI models, like Ollama, OpenAI, etc.

The ml_model_list submodule contains a list of models that can be used for machine learning tasks. More can easily be added, but we keep a list here of models that are known to work well with Kiln's structured data and tool calling systems.

The prompt_builders submodule contains classes that build prompts for use with the AI agents.

The repair submodule contains an adapter for the repair task.

The parser submodule contains parsers for the output of the AI models.

The eval submodule contains the code for evaluating the performance of a model.

Submodules are loaded lazily via PEP 562 __getattr__ to avoid pulling in heavy
transitive dependencies (litellm, llama_index, numpy, etc.) when only a
lightweight submodule is needed -- e.g. in multiprocessing.spawn child processes
that only need eval_helpers.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . import (
        chat,
        chunkers,
        data_gen,
        eval,
        extractors,
        fine_tune,
        ml_embedding_model_list,
        ml_model_list,
        model_adapters,
        prompt_builders,
        remote_config,
        repair,
    )

__all__ = [
    "chat",
    "chunkers",
    "data_gen",
    "eval",
    "extractors",
    "fine_tune",
    "ml_embedding_model_list",
    "ml_model_list",
    "model_adapters",
    "prompt_builders",
    "remote_config",
    "repair",
]


def __getattr__(name: str) -> object:
    if name in __all__:
        return importlib.import_module(f".{name}", __name__)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return __all__
