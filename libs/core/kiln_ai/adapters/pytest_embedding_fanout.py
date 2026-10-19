"""Shared parametrization helpers for the embedding fan-out tests.

Several test modules fan out across every (model, provider) combination in
ml_embedding_model_list.py. They need two different views of that list, and
picking the wrong one is a silent failure in either direction, so both live
here rather than being re-derived per module:

- `all_embedding_model_provider_pairs` — every entry, including deprecated
  ones. Use it for offline tests. A deprecated entry stays in the model list
  so that an existing embedding config keeps resolving (and shows the
  deprecation warning), so lookup and transformation tests must keep covering
  it.
- `live_embedding_model_provider_pairs` — only entries that can serve a
  request. Use it for @pytest.mark.paid tests. A deprecated entry always
  fails a live call, so including it would just add a guaranteed failure.
"""

from kiln_ai.adapters.ml_embedding_model_list import built_in_embedding_models
from kiln_ai.datamodel.datamodel_enums import ModelProviderName

# KilnEmbeddingModel.name is declared `str`, not EmbeddingModelName.
EmbeddingModelProviderPair = tuple[str, ModelProviderName]


def all_embedding_model_provider_pairs() -> list[EmbeddingModelProviderPair]:
    """Every (model, provider) pair in the embedding model list, deprecated included."""
    return [
        (model.name, provider.name)
        for model in built_in_embedding_models
        for provider in model.providers
    ]


def live_embedding_model_provider_pairs() -> list[EmbeddingModelProviderPair]:
    """Every (model, provider) pair that can still serve a live request."""
    return [
        (model.name, provider.name)
        for model in built_in_embedding_models
        for provider in model.providers
        if not provider.deprecated
    ]
