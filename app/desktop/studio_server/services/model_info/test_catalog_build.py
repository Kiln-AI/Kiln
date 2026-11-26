import copy
import json
from pathlib import Path
from typing import Any

import pytest
from kiln_ai.adapters.ml_model_list import KilnModel, KilnModelProvider
from kiln_ai.adapters.ml_provider_list import KilnProviderInfo, built_in_providers
from kiln_ai.adapters.remote_config import deserialize_config_data
from kiln_ai.datamodel.datamodel_enums import ModelProviderName

from app.desktop.studio_server.services.model_info.catalog_build import (
    KilnModelList,
    ModelsDevData,
    build_catalog,
    parse_models_dev,
)
from app.desktop.studio_server.services.model_info.catalog_schema import (
    Catalog,
    CatalogEntry,
)

TEST_DATA = Path(__file__).parent / "test_data"


def kiln_file() -> dict[str, Any]:
    """A slice of Kiln's published remote config: 7 models, 5 providers."""
    return json.loads((TEST_DATA / "kiln_config.json").read_text())


def models_dev_file() -> dict[str, Any]:
    """A slice of models.dev's api.json."""
    return json.loads((TEST_DATA / "models_dev.json").read_text())


def fixture_providers(kiln_raw: dict[str, Any]) -> tuple[KilnProviderInfo, ...]:
    """The file's `provider_list`, then Kiln's built-in providers it lacks."""
    listed = tuple(
        KilnProviderInfo.model_validate(p) for p in kiln_raw.get("provider_list", [])
    )
    ids = {p.id for p in listed}
    return listed + tuple(p for p in built_in_providers if p.id not in ids)


def kiln_list(
    kiln_raw: dict[str, Any] | None = None,
    providers: tuple[KilnProviderInfo, ...] | None = None,
) -> KilnModelList:
    raw = kiln_file() if kiln_raw is None else kiln_raw
    models = deserialize_config_data(copy.deepcopy(raw)).model_list
    return KilnModelList(
        models=tuple(models),
        providers=fixture_providers(raw) if providers is None else providers,
        loaded_at=None,
    )


def models_dev(raw: Any) -> ModelsDevData:
    return parse_models_dev(json.dumps(raw, ensure_ascii=False).encode())


def build(
    kiln_raw: dict[str, Any] | None = None,
    models_dev_raw: dict[str, Any] | None = None,
    providers: tuple[KilnProviderInfo, ...] | None = None,
) -> Catalog:
    md = models_dev(models_dev_file() if models_dev_raw is None else models_dev_raw)
    return build_catalog(kiln_list(kiln_raw, providers), md)


def one_model(*providers: dict[str, Any], **fields: Any) -> dict[str, Any]:
    """A Kiln file with one model on the given provider entries."""
    model = {"name": "m", "friendly_name": "M", "family": "f", **fields}
    return {"model_list": [{**model, "providers": list(providers)}]}


def models_dev_with(provider: str, model_id: str, **entry: Any) -> dict[str, Any]:
    return {provider: {"id": provider, "models": {model_id: entry}}}


def entry_of(catalog: Catalog, model: str, provider: str) -> CatalogEntry:
    found = catalog.model(model)
    assert found is not None
    (entry,) = [e for e in found.entries if e.provider == provider]
    return entry


def test_the_fixture_builds_with_prices_limits_and_dates():
    catalog = build()
    assert [m.model for m in catalog.models] == [
        "claude_sonnet_5_5",
        "gpt_6_1_sol",
        "gemini_3_8_flash",
        "deepseek_4_pro",
        "qwen_3p8_max_0902",
        "glm_4_6",
        "jev_1_13",
    ]
    gpt = catalog.model("gpt_6_1_sol")
    assert gpt is not None
    assert (gpt.display_name, gpt.family, gpt.kiln_featured_rank) == (
        "GPT-6.1 Sol",
        "gpt",
        4,
    )
    assert gpt.release_date == "2026-09-29" and gpt.release_date_estimated is False
    assert (gpt.knowledge_cutoff, gpt.open_weights) == ("2026-04-30", False)
    assert (gpt.context_window, gpt.max_output_tokens) == (1050000, 128000)
    openai = entry_of(catalog, "gpt_6_1_sol", "openai")
    assert openai.provider_model_id == "gpt-6.1-sol"
    assert (openai.input_price, openai.output_price) == (2.0, 10.0)
    assert (openai.cache_read_price, openai.cache_write_price) == (0.1, 2.5)
    assert openai.supports_temperature is False
    assert openai.thinking_levels == ["none", "low", "medium", "high"]
    assert openai.default_thinking_level == "medium"
    assert openai.kiln_suggested_for == ["eval_judge", "synthetic_data"]
    assert openai.supports_tools is False and openai.supports_vision is True
    assert openai.default_structured_output_mode == "json_schema"
    assert openai.tags == ["fast"]
    assert gpt.agent_notes is not None and gpt.agent_notes.startswith("Follows")
    assert gpt.tags == ["strong_agentic", "strong_coding"]
    assert [p.provider for p in catalog.providers[:5]] == [
        "openai",
        "openrouter",
        "cloudflare",
        "featherless_ai",
        "typesafe",
    ]
    openrouter = catalog.provider("openrouter")
    assert openrouter is not None and openrouter.name == "OpenRouter"
    assert openrouter.notes is not None and openrouter.models_dev_id == "openrouter"
    ollama = catalog.provider("ollama")
    assert ollama is not None and ollama.models_dev_id is None
    dated = [m.model for m in catalog.models if m.release_date is not None]
    assert dated == [m.model for m in catalog.models if m.model != "jev_1_13"]


def test_price_is_matched_on_the_exact_pair():
    catalog = build()
    openrouter = entry_of(catalog, "deepseek_4_pro", "openrouter")
    siliconflow = entry_of(catalog, "deepseek_4_pro", "siliconflow_cn")
    assert (openrouter.input_price, openrouter.output_price) == (0.9, 1.5)
    assert siliconflow.input_price == pytest.approx(1.79336973)
    assert siliconflow.context_window == 1049000
    # No models.dev entry for this pair: nothing is borrowed from another one.
    featherless = entry_of(catalog, "deepseek_4_pro", "featherless_ai")
    assert featherless.input_price is None and featherless.context_window is None
    deprecated = entry_of(catalog, "deepseek_4_pro", "fireworks_ai")
    assert deprecated.deprecated is True and deprecated.input_price is None


def test_model_facts_follow_the_provider_preference():
    kiln = kiln_file()
    deepseek = next(m for m in kiln["model_list"] if m["name"] == "deepseek_4_pro")
    # OpenRouter last in Kiln's order: the preference, not the order, decides.
    deepseek["providers"].append(deepseek["providers"].pop(0))
    model = build(kiln).model("deepseek_4_pro")
    assert model is not None
    assert model.release_date == "2026-04-24"
    assert model.max_output_tokens == 393216  # OpenRouter's, not SiliconFlow's
    # Without OpenRouter, the other providers by id: cloudflare before
    # siliconflow_cn.
    deepseek["providers"] = [
        p for p in deepseek["providers"] if p["name"] != "openrouter"
    ]
    model = build(kiln).model("deepseek_4_pro")
    assert model is not None and model.release_date == "2026-08-13"


def test_the_loose_match_dates_a_model_with_no_exact_match():
    glm = build().model("glm_4_6")
    assert glm is not None
    assert glm.release_date == "2025-09-30" and glm.release_date_estimated is True
    # The other model facts are not taken from a loose match.
    assert glm.open_weights is None and glm.context_window is None
    assert all(e.input_price is None for e in glm.entries)
    jev = build().model("jev_1_13")
    assert jev is not None
    assert jev.release_date is None and jev.release_date_estimated is False


def test_the_loose_match_takes_the_earliest_date():
    md = {
        "a": {"models": {"vendor/Big-Model-2": {"release_date": "2026-03-01"}}},
        "b": {
            "models": {
                "big-model-2": {"release_date": "2025-12-01T00:00:00Z"},
                "other": {
                    "release_date": "2025-06-01",
                    "canonical_model_id": "lab/big.model.2",
                },
                "bad-date": {"release_date": "soon", "canonical_model_id": "bigmodel2"},
            }
        },
    }
    kiln = one_model({"name": "openrouter", "model_id": "x/big_model_2:free"})
    model = build(kiln, md).model("m")
    assert model is not None
    assert model.release_date == "2025-06-01" and model.release_date_estimated


def test_a_loose_date_counts_a_deprecated_entry():
    md = {"z": {"models": {"old-name-1": {"release_date": "2025-01-02"}}}}
    kiln = one_model(
        {"name": "openai", "model_id": "new-name"},
        {"name": "groq", "model_id": "old-name-1", "deprecated": True},
    )
    model = build(kiln, md).model("m")
    assert model is not None and model.release_date == "2025-01-02"


def test_a_short_loose_key_is_not_used():
    md = {"z": {"models": {"o3": {"release_date": "2025-04-16"}}}}
    model = build(one_model({"name": "openai", "model_id": "o-3"}), md).model("m")
    assert model is not None and model.release_date is None


def test_an_exact_match_with_no_date_falls_back_to_the_loose_date():
    md = {
        "openai": {"models": {"gpt-x-1": {"limit": {"context": 1000}}}},
        "other": {"models": {"gpt-x-1": {"release_date": "2025-05-05"}}},
    }
    found = build(one_model({"name": "openai", "model_id": "gpt-x-1"}), md).model("m")
    assert found is not None
    assert found.context_window == 1000
    assert (found.release_date, found.release_date_estimated) == ("2025-05-05", True)


def priced(canonical: str, input_price: Any, output_price: Any = 1.0) -> dict:
    """A models.dev entry of a canonical model, with these prices."""
    return {
        "canonical_model_id": canonical,
        "cost": {"input": input_price, "output": output_price},
    }


def test_the_median_price_is_across_every_models_dev_provider():
    # One cheap host on OpenRouter, three hosts at the typical price, a $0
    # coding plan, an entry with no price, and another canonical model.
    md = {
        "openrouter": {"models": {"k/k3": priced("k/k3", 0.192, 0.8)}},
        "a": {"models": {"k3": priced("k/k3", 3.0, 12.0)}},
        "b": {"models": {"k3": priced("k/k3", 2.9, 11.0)}},
        "c": {"models": {"k3": priced("k/k3", 3.1, 13.0)}},
        "plan": {"models": {"k3": priced("k/k3", 0, 0)}},
        "d": {"models": {"k3": {"canonical_model_id": "k/k3"}}},
        "e": {"models": {"k2": priced("k/k2", 99.0, 99.0)}},
    }
    catalog = build(one_model({"name": "openrouter", "model_id": "k/k3"}), md)
    found = catalog.model("m")
    assert found is not None
    assert (found.median_input_price, found.median_output_price) == (2.95, 11.5)
    # The entry keeps its own price.
    assert entry_of(catalog, "m", "openrouter").input_price == 0.192


def test_the_median_needs_three_paid_prices():
    md = {
        "openrouter": {"models": {"k3": priced("k/k3", 1.0, 2.0)}},
        "a": {"models": {"k3": priced("k/k3", 3.0, 0)}},
        "b": {"models": {"k3": priced("k/k3", 5.0, None)}},
    }
    found = build(one_model({"name": "openrouter", "model_id": "k3"}), md).model("m")
    assert found is not None
    assert (found.median_input_price, found.median_output_price) == (3.0, None)
    # The fixture: three priced gemini entries, two deepseek ones.
    catalog = build()
    gemini = catalog.model("gemini_3_8_flash")
    assert gemini is not None
    assert (gemini.median_input_price, gemini.median_output_price) == (0.75, 3.75)
    deepseek = catalog.model("deepseek_4_pro")
    assert deepseek is not None and deepseek.median_input_price is None


def test_a_provider_with_many_entries_counts_once_at_its_lowest_price():
    # Provider a lists the model three times: an alias, a fast tier and a
    # $0 plan. It counts once, at its lowest paid price, input and output
    # each on their own.
    md = {
        "a": {
            "models": {
                "k3": priced("k/k3", 3.0, 16.0),
                "k3-fast": priced("k/k3", 4.0, 12.0),
                "k3-plan": priced("k/k3", 0, 0),
            }
        },
        "groq": {"models": {"k3": priced("k/k3", 5.0, 20.0)}},
    }
    kiln = one_model({"name": "groq", "model_id": "k3"})
    found = build(kiln, md).model("m")
    assert found is not None
    # Two providers, not four entries: no median.
    assert (found.median_input_price, found.median_output_price) == (None, None)
    md["c"] = {"models": {"k3": priced("k/k3", 6.0, 24.0)}}
    found = build(kiln, md).model("m")
    assert found is not None
    assert (found.median_input_price, found.median_output_price) == (5.0, 20.0)


def test_the_canonical_id_and_reasoning_follow_the_provider_preference():
    md = {
        "openrouter": {"models": {"x": {"reasoning": True}}},
        "groq": {"models": {"x": {**priced("lab/x", 2.0), "reasoning": False}}},
        "a": {"models": {"x": priced("lab/x", 4.0)}},
        "b": {"models": {"x": priced("lab/x", 6.0)}},
    }
    kiln = one_model(
        {"name": "groq", "model_id": "x"}, {"name": "openrouter", "model_id": "x"}
    )
    found = build(kiln, md).model("m")
    assert found is not None
    # OpenRouter's entry has no canonical id: groq's gives the median.
    assert found.reasoning_model is True and found.median_input_price == 4.0
    md["openrouter"]["models"]["x"]["reasoning"] = "yes"
    found = build(kiln, md).model("m")
    assert found is not None and found.reasoning_model is None


def test_kiln_suggested_for_has_the_clear_names():
    sonnet = entry_of(build(), "claude_sonnet_5_5", "anthropic")
    assert sonnet.kiln_suggested_for == [
        "eval_judge",
        "synthetic_data",
        "synthetic_user",
    ]
    kiln = one_model(
        {
            "name": "openai",
            "suggested_for_doc_extraction": True,
            "suggested_for_uncensored_data_gen": True,
        }
    )
    assert entry_of(build(kiln), "m", "openai").kiln_suggested_for == [
        "document_extraction"
    ]


def test_the_models_dev_id_is_used():
    kiln = one_model({"name": "together_ai", "model_id": "m-1"})
    md = {
        **models_dev_with("togetherai", "m-1", cost={"input": 9}),
        **models_dev_with("together-v2", "m-1", cost={"input": 1}),
    }
    assert entry_of(build(kiln, md), "m", "together_ai").input_price == 9.0
    providers = (
        KilnProviderInfo(
            id=ModelProviderName.together_ai,
            friendly_name="Together",
            models_dev_id="together-v2",
        ),
    )
    catalog = build(kiln, md, providers)
    assert entry_of(catalog, "m", "together_ai").input_price == 1.0


def test_a_provider_without_models_dev_id_is_not_joined():
    kiln = one_model({"name": "huggingface", "model_id": "org/m-1"})
    md = models_dev_with("huggingface", "org/m-1", cost={"input": 1})
    assert entry_of(build(kiln, md), "m", "huggingface").input_price == 1.0
    providers = (
        KilnProviderInfo(id=ModelProviderName.huggingface, friendly_name="HF"),
    )
    assert entry_of(build(kiln, md, providers), "m", "huggingface").input_price is None
    # A provider Kiln has no info for is not joined either.
    assert entry_of(build(kiln, md, ()), "m", "huggingface").input_price is None


def test_a_bad_price_and_a_bad_limit_are_dropped():
    catalog = build()
    qwen = entry_of(catalog, "qwen_3p8_max_0902", "openrouter")
    assert qwen.cache_read_price is None  # negative in the fixture
    assert qwen.input_price == 2.0
    anthropic = entry_of(catalog, "claude_sonnet_5_5", "anthropic")
    assert anthropic.max_output_tokens is None  # a string in the fixture
    assert anthropic.context_window == 1000000
    md = models_dev_with(
        "openai",
        "m-1",
        cost={
            "input": float("nan"),
            "output": float("inf"),
            "cache_read": True,
            "cache_write": "1",
        },
        limit={"context": 0, "output": True},
        temperature="yes",
    )
    kiln = one_model({"name": "openai", "model_id": "m-1"})
    entry = entry_of(build(kiln, md), "m", "openai")
    assert entry.input_price is None and entry.output_price is None
    assert entry.cache_read_price is None and entry.cache_write_price is None
    assert entry.context_window is None and entry.max_output_tokens is None
    assert entry.supports_temperature is None
    zero = models_dev_with("openai", "m-1", cost={"input": 0})
    assert entry_of(build(kiln, zero), "m", "openai").input_price == 0.0
    huge = models_dev_with("openai", "m-1", cost={"input": 10**400})
    assert entry_of(build(kiln, huge), "m", "openai").input_price is None


def kiln_model(name: str = "m", **fields: Any) -> KilnModel:
    return KilnModel(
        **{
            "name": name,
            "friendly_name": name.upper(),
            "family": "f",
            "providers": [KilnModelProvider(name=ModelProviderName.openai)],
            **fields,
        }
    )


def build_models(
    *models: KilnModel, providers: tuple[KilnProviderInfo, ...] = ()
) -> Catalog:
    return build_catalog(
        KilnModelList(models=models, providers=providers, loaded_at=None), None
    )


def test_tags_are_cleaned_deduplicated_and_capped():
    tags = ["fast", "Fast", "very fast", "fast", "x" * 41, "a" * 40, ""]
    tags += [f"t{i}" for i in range(20)]
    provider = KilnModelProvider(name=ModelProviderName.openai, tags=["Fast"])
    info = KilnProviderInfo(
        id=ModelProviderName.openai, friendly_name="OpenAI", tags=["zdr", "ZDR"]
    )
    catalog = build_models(
        kiln_model(tags=tags, providers=[provider]), providers=(info,)
    )
    model = catalog.model("m")
    assert model is not None
    assert model.tags == ["fast", "a" * 40] + [f"t{i}" for i in range(10)]
    assert model.entries[0].tags == []
    openai = catalog.provider("openai")
    assert openai is not None and openai.tags == ["zdr"]


def test_a_long_note_is_cut():
    info = KilnProviderInfo(
        id=ModelProviderName.openai, friendly_name="OpenAI", notes="x" * 2000
    )
    catalog = build_models(
        kiln_model(agent_notes="word " * 500, editorial_notes="  "),
        providers=(info,),
    )
    model = catalog.model("m")
    assert model is not None and model.agent_notes is not None
    assert len(model.agent_notes) <= 2000
    assert model.agent_notes.endswith("word [cut]")
    assert model.editorial_notes is None
    openai = catalog.provider("openai")
    assert openai is not None and openai.notes == "x" * 2000


def test_a_duplicate_model_name_keeps_the_first():
    catalog = build_models(
        kiln_model(friendly_name="First"), kiln_model(friendly_name="Second")
    )
    assert [(m.model, m.display_name) for m in catalog.models] == [("m", "First")]


def test_a_model_without_family_or_friendly_name():
    catalog = build_models(kiln_model(family="", friendly_name=""))
    model = catalog.model("m")
    assert model is not None and (model.family, model.display_name) == (None, "m")


def test_a_lookup_does_not_change_equality():
    catalog = build()
    copy_ = catalog.model_copy(deep=True)
    assert catalog.model("glm_4_6") is not None
    assert catalog.provider("openai") is not None
    assert catalog == copy_


def test_no_models_dev_gives_null_prices_and_kiln_data():
    catalog = build_catalog(kiln_list(), None)
    assert len(catalog.models) == 7
    assert all(m.release_date is None for m in catalog.models)
    assert all(e.input_price is None for m in catalog.models for e in m.entries)
    gpt = catalog.model("gpt_6_1_sol")
    assert gpt is not None and gpt.kiln_featured_rank == 4 and gpt.tags
    assert entry_of(catalog, "gpt_6_1_sol", "openai").thinking_levels


@pytest.mark.parametrize(
    "body,reason",
    [
        (b"{not json", "not valid JSON"),
        (b"\xff\xfe", "not valid JSON"),
        (b"[" * 100_000 + b"]" * 100_000, "not valid JSON"),
        (b'["not", "an", "object"]', "not an object"),
        (b"null", "not an object"),
    ],
)
def test_parse_models_dev_rejects_bad_json_and_a_non_object(body, reason):
    with pytest.raises(ValueError) as error:
        parse_models_dev(body)
    assert str(error.value) == reason


def test_parse_models_dev_keeps_only_the_joined_keys():
    data = models_dev(
        {
            "p": {
                "id": "p",
                "name": "P",
                "models": {
                    "m": {
                        "id": "m",
                        "modalities": {"input": ["text"]},
                        "cost": {"input": 1, "output": 2, "reasoning": 3},
                        "limit": {"context": 10, "input": 8, "output": 5},
                        "release_date": "2025-01-01",
                        "reasoning": True,
                        "tool_call": True,
                    },
                    "not an entry": 7,
                },
            },
            "q": "not a provider",
        }
    )
    assert data.providers == {
        "p": {
            "models": {
                "m": {
                    "cost": {"input": 1, "output": 2},
                    "limit": {"context": 10, "output": 5},
                    "release_date": "2025-01-01",
                    "reasoning": True,
                }
            }
        },
        "q": {"models": {}},
    }
    assert data.loose_dates == {}  # the key "m" is too short
