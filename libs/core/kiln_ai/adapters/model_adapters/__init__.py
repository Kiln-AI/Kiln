"""
# Model Adapters

Model adapters are used to call AI models, like Ollama, OpenAI, etc.

"""

from . import (
    base_adapter,
    litellm_adapter,
)

__all__ = [
    "base_adapter",
    "litellm_adapter",
]
