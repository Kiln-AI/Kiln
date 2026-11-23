"""Response models of the model info endpoints (`model_info_api.py`). All
prices are USD per million tokens; null means "no price data", not "free"."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ModelInfoStatus = Literal["ready", "not_offered", "not_connected"]

PER_MTOK = "USD per million tokens"
MEDIAN = f"{PER_MTOK}: the median price across the providers on models.dev."
UNTESTED = (
    "Kiln has not tested this model, usually one a user added. The supports_*"
    " fields do not apply."
)
KILN_FEATURED_RANK = "Kiln's ranking, 1 first. Null: not featured."
REASONING_MODEL = (
    "The model reasons before it answers, also when that is always on (models.dev)."
)
HAS_THINKING_LEVELS = (
    "At least one listed provider entry has thinking levels that a run config can set."
)
STATUS = (
    "ready: the user can run the model on this provider now. not_offered: the"
    " provider is connected, but does not offer this model (for example an Ollama"
    " model that is not installed). not_connected: the provider is not connected"
    " in Kiln."
)


def _price(what: str) -> str:
    return f"{what}, {PER_MTOK}. Null: no price data."


class ModelInfoKilnSource(BaseModel):
    """Where Kiln's model list came from, and how old it is."""

    origin: Literal["remote_config", "built_in"] = Field(
        description="remote_config: Kiln's remote model list was loaded in this"
        " process. built_in: the list shipped with the installed app."
    )
    loaded_at: datetime | None = Field(
        default=None,
        description="UTC time of the last good remote model list load. Null for built_in.",
    )
    age_seconds: int | None = Field(
        default=None, description="Seconds since loaded_at. Null for built_in."
    )


class ModelInfoModelsDevSource(BaseModel):
    """The state and age of the models.dev data."""

    state: Literal["ok", "stale", "unavailable"] = Field(
        description="ok: models.dev data younger than 6 hours. stale: older data is"
        " served, because a refresh failed or did not finish in time. unavailable:"
        " no models.dev data; every price, limit and date is null."
    )
    loaded_at: datetime | None = Field(
        default=None,
        description="UTC time the models.dev data was fetched, or last confirmed unchanged.",
    )
    age_seconds: int | None = Field(
        default=None, description="Seconds since loaded_at."
    )
    detail: str | None = Field(
        default=None,
        description="Null when ok. Else why the data is missing or old: turned off,"
        " loading, not loaded, refresh running, or the last failure reason.",
    )


class ModelInfoSources(BaseModel):
    """Which data an answer is built from, and how old it is."""

    kiln_model_list: ModelInfoKilnSource
    models_dev: ModelInfoModelsDevSource


class ModelInfoProviderEntryRow(BaseModel):
    """One provider entry of a model in a list row: status and prices."""

    provider: str = Field(description="Kiln provider id.")
    status: ModelInfoStatus = Field(description=STATUS)
    input_price: float | None = Field(default=None, description=_price("Input price"))
    output_price: float | None = Field(default=None, description=_price("Output price"))
    tags: list[str] = Field(
        default_factory=list, description="Kiln's tags for this provider entry."
    )
    deprecated: bool = Field(
        default=False, description="Kiln marks this provider entry deprecated."
    )


class ModelInfoRow(BaseModel):
    """One model in a list of models, with its provider entries."""

    model: str = Field(description="Kiln's model id. Use it in a run config.")
    display_name: str = Field(description="The model's name as Kiln shows it.")
    family: str | None = Field(default=None, description="Kiln's model family.")
    kiln_featured_rank: int | None = Field(default=None, description=KILN_FEATURED_RANK)
    tags: list[str] = Field(
        default_factory=list,
        description="Kiln's model tags, for example current, recommended, top_value.",
    )
    release_date: str | None = Field(
        default=None, description="ISO date, from models.dev."
    )
    context_window: int | None = Field(
        default=None, description="Tokens, from models.dev."
    )
    open_weights: bool | None = Field(default=None, description="From models.dev.")
    reasoning_model: bool | None = Field(default=None, description=REASONING_MODEL)
    has_thinking_levels: bool = Field(default=False, description=HAS_THINKING_LEVELS)
    median_input_price: float | None = Field(default=None, description=MEDIAN)
    median_output_price: float | None = Field(default=None, description=MEDIAN)
    editorial_notes: str | None = Field(
        default=None,
        description="Kiln's notes for people. Null unless include_notes is true.",
    )
    agent_notes: str | None = Field(
        default=None,
        description="Kiln's notes for an agent that chooses or configures the model."
        " Null unless include_notes is true.",
    )
    providers: list[ModelInfoProviderEntryRow] = Field(
        default_factory=list, description="The provider entries that pass the filters."
    )


class ModelInfoList(BaseModel):
    """A page of models, with the sources the answer is built from."""

    sources: ModelInfoSources
    total: int = Field(description="Rows after all filters, the same on every page.")
    fuzzy_match: bool = Field(
        default=False,
        description="True: no model held the search words, and the rows are the"
        " closest names.",
    )
    models: list[ModelInfoRow] = Field(default_factory=list)


class ModelInfoProviderEntryDetails(BaseModel):
    """The full record of one provider entry of a model."""

    provider: str = Field(description="Kiln provider id.")
    status: ModelInfoStatus = Field(description=STATUS)
    provider_model_id: str | None = Field(
        default=None,
        description="The provider's own id for the model. Null for a model Kiln"
        " only knows from the user's setup.",
    )
    deprecated: bool = Field(
        default=False, description="Kiln marks this provider entry deprecated."
    )
    untested: bool = Field(default=False, description=UNTESTED)
    input_price: float | None = Field(default=None, description=_price("Input price"))
    output_price: float | None = Field(default=None, description=_price("Output price"))
    cache_read_price: float | None = Field(
        default=None, description=_price("Cache read price")
    )
    cache_write_price: float | None = Field(
        default=None, description=_price("Cache write price")
    )
    context_window: int | None = Field(
        default=None,
        description="This provider's context window in tokens, from models.dev.",
    )
    max_output_tokens: int | None = Field(
        default=None,
        description="This provider's output limit in tokens, from models.dev.",
    )
    tags: list[str] = Field(
        default_factory=list, description="Kiln's tags for this provider entry."
    )
    supports_tools: bool | None = Field(
        default=None, description="Kiln's flag: tool calls work on this pair."
    )
    supports_structured_output: bool | None = Field(
        default=None, description="Kiln's flag: structured output works on this pair."
    )
    supports_vision: bool | None = Field(
        default=None, description="Kiln's flag: image input works on this pair."
    )
    supports_temperature: bool | None = Field(
        default=None, description="From models.dev."
    )
    thinking_levels: list[str] = Field(
        default_factory=list,
        description="The thinking levels a run config can set, in Kiln's order.",
    )
    default_thinking_level: str | None = Field(
        default=None,
        description="Kiln's suggested default thinking level for the pair. Null"
        " when Kiln suggests none.",
    )
    default_structured_output_mode: str | None = Field(
        default=None, description="Kiln's suggested default output mode for the pair."
    )
    kiln_suggested_for: list[str] = Field(
        default_factory=list,
        description="Uses that Kiln suggests the model for: eval_judge,"
        " synthetic_data, document_extraction, synthetic_user.",
    )


class ModelInfoDetails(BaseModel):
    """The full record of one model, with every provider entry."""

    sources: ModelInfoSources
    model: str = Field(description="Kiln's model id. Use it in a run config.")
    display_name: str = Field(description="The model's name as Kiln shows it.")
    family: str | None = Field(default=None, description="Kiln's model family.")
    kiln_featured_rank: int | None = Field(default=None, description=KILN_FEATURED_RANK)
    tags: list[str] = Field(default_factory=list, description="Kiln's model tags.")
    release_date: str | None = Field(
        default=None, description="ISO date, from models.dev."
    )
    release_date_estimated: bool = Field(
        default=False,
        description="True: the date came from a match on the model's name only.",
    )
    knowledge_cutoff: str | None = Field(
        default=None, description="As models.dev writes it."
    )
    context_window: int | None = Field(
        default=None, description="Tokens, from models.dev."
    )
    max_output_tokens: int | None = Field(
        default=None, description="Tokens, from models.dev."
    )
    open_weights: bool | None = Field(default=None, description="From models.dev.")
    reasoning_model: bool | None = Field(default=None, description=REASONING_MODEL)
    has_thinking_levels: bool = Field(default=False, description=HAS_THINKING_LEVELS)
    median_input_price: float | None = Field(default=None, description=MEDIAN)
    median_output_price: float | None = Field(default=None, description=MEDIAN)
    editorial_notes: str | None = Field(
        default=None, description="Kiln's notes for people."
    )
    agent_notes: str | None = Field(
        default=None,
        description="Kiln's notes for an agent that chooses or configures the model.",
    )
    providers: list[ModelInfoProviderEntryDetails] = Field(
        default_factory=list,
        description="Every provider entry, also deprecated and not available ones.",
    )


class ModelInfoProviderRow(BaseModel):
    """One model provider: whether it is connected, and how many models are ready on it."""

    provider: str = Field(description="Kiln provider id.")
    name: str | None = Field(default=None, description="The provider's name in Kiln.")
    status: Literal["connected", "not_connected"] = Field(
        description="connected: the provider is set up in Kiln."
    )
    ready_model_count: int = Field(
        default=0,
        description="Models the user can run on this provider now, deprecated and"
        " untested ones included.",
    )
    tags: list[str] = Field(default_factory=list, description="Kiln's provider tags.")
    notes: str | None = Field(
        default=None,
        description="Kiln's provider notes: data retention, rate limits, gotchas.",
    )


class ModelInfoProviderList(BaseModel):
    """Every model provider Kiln knows, with the sources the answer is built from."""

    sources: ModelInfoSources
    providers: list[ModelInfoProviderRow] = Field(default_factory=list)
