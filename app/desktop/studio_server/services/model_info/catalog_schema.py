"""The model catalogue: Kiln's model list with the models.dev facts joined on
(`catalog_build.py`). Prices are USD per million tokens."""

from functools import cached_property

from pydantic import BaseModel, Field


class CatalogEntry(BaseModel):
    """One provider entry of one model."""

    provider: str  # Kiln's provider id
    provider_model_id: str | None = None  # the provider's own id for the model
    deprecated: bool = False
    # Kiln has not tested the model, usually one a user added.
    untested: bool = False
    supports_tools: bool | None = None
    supports_structured_output: bool | None = None
    supports_vision: bool | None = None
    # The values of Kiln's `available_thinking_levels`, in Kiln's order.
    thinking_levels: list[str] = Field(default_factory=list)
    default_thinking_level: str | None = None
    # Kiln's suggested default output mode for the pair.
    default_structured_output_mode: str | None = None
    # Values of `KILN_SUGGESTED_FOR` (`catalog_build.py`).
    kiln_suggested_for: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    # From models.dev. Null when this entry has no exact match. A price of 0
    # is kept as it is: usually a free tier, not the paid price.
    input_price: float | None = None
    output_price: float | None = None
    cache_read_price: float | None = None
    cache_write_price: float | None = None
    context_window: int | None = None
    max_output_tokens: int | None = None
    supports_temperature: bool | None = None


class CatalogModel(BaseModel):
    model: str  # Kiln's model id (KilnModel.name)
    display_name: str  # friendly_name
    family: str | None = None
    kiln_featured_rank: int | None = None  # 1 first
    editorial_notes: str | None = None
    agent_notes: str | None = None
    tags: list[str] = Field(default_factory=list)
    entries: list[CatalogEntry] = Field(default_factory=list)
    # The model facts from models.dev: the first matched entry, except the
    # release date, which has a loose fallback (`release_date_estimated`).
    release_date: str | None = None  # ISO date "YYYY-MM-DD"
    release_date_estimated: bool = False
    knowledge_cutoff: str | None = None
    open_weights: bool | None = None
    # models.dev's `reasoning`: the model reasons before it answers, also
    # when the reasoning is always on.
    reasoning_model: bool | None = None
    context_window: int | None = None
    max_output_tokens: int | None = None
    # The median across the models.dev providers of the model's canonical
    # id, one price per provider (its lowest), $0 left out. Null with fewer
    # than `MIN_MEDIAN_PRICES` priced providers.
    median_input_price: float | None = None
    median_output_price: float | None = None


class CatalogProvider(BaseModel):
    provider: str
    name: str | None = None
    notes: str | None = None
    tags: list[str] = Field(default_factory=list)
    models_dev_id: str | None = None


class Catalog(BaseModel):
    models: list[CatalogModel] = Field(default_factory=list)  # in Kiln's order
    providers: list[CatalogProvider] = Field(default_factory=list)

    @cached_property
    def _models_by_id(self) -> dict[str, CatalogModel]:
        return {m.model: m for m in self.models}

    @cached_property
    def _providers_by_id(self) -> dict[str, CatalogProvider]:
        return {p.provider: p for p in self.providers}

    def model(self, model_id: str) -> CatalogModel | None:
        return self._models_by_id.get(model_id)

    def provider(self, provider_id: str) -> CatalogProvider | None:
        return self._providers_by_id.get(provider_id)
