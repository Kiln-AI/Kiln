from typing import Any

import pytest
from kiln_ai.adapters.ml_model_list import KilnModel, KilnModelProvider
from kiln_ai.datamodel.datamodel_enums import ModelProviderName

from app.desktop.studio_server.api_models.model_info_models import (
    ModelInfoKilnSource,
    ModelInfoList,
    ModelInfoModelsDevSource,
    ModelInfoProviderEntryRow,
    ModelInfoSources,
)
from app.desktop.studio_server.services.model_info.catalog_build import (
    KilnModelList,
    build_catalog,
)
from app.desktop.studio_server.services.model_info.catalog_schema import Catalog
from app.desktop.studio_server.services.model_info.test_catalog_build import (
    build,
    kiln_list,
)
from app.desktop.studio_server.services.model_info.view import (
    InvalidModelQueryError,
    ListModelsQuery,
    ModelNotFoundError,
    Offered,
    list_models,
    list_providers,
    model_details,
    search_rows,
    status,
)

FINE_TUNE = "424242975950::424242783061::424242300001"
CATALOG = build()
SOURCES = ModelInfoSources(
    kiln_model_list=ModelInfoKilnSource(origin="built_in"),
    models_dev=ModelInfoModelsDevSource(state="ok"),
)

# What a Kiln with keys for OpenRouter, OpenAI and Anthropic offers.
SERVER: dict[str, list[str]] = {
    "openrouter": [
        "claude_sonnet_5_5",
        "gpt_6_1_sol",
        "gemini_3_8_flash",
        "deepseek_4_pro",
        "qwen_3p8_max_0902",
        "glm_4_6",
    ],
    "openai": ["gpt_6_1_sol"],
    "anthropic": ["claude_sonnet_5_5"],
}


def payload(
    server: dict[str, list[str]] | None = None, **extra: dict[str, Any]
) -> list[dict[str, Any]]:
    """An `/api/available_models` payload. A pair in the catalogue has the
    catalogue's thinking levels and output mode, as in a Kiln that loaded the
    same model list. `extra` maps a provider to one more model dict on it."""
    server = SERVER if server is None else server
    rows = [
        {
            "provider_id": provider,
            "provider_name": provider.title(),
            "models": [server_model(provider, model) for model in models],
        }
        for provider, models in server.items()
    ]
    for provider, model in extra.items():
        row = next((r for r in rows if r["provider_id"] == provider), None)
        if row is None:
            row = {"provider_id": provider, "models": []}
            rows.append(row)
        row["models"].append(model)
    return rows


def server_model(provider: str, model: str) -> dict[str, Any]:
    row: dict[str, Any] = {"id": model, "name": model.upper()}
    found = CATALOG.model(model)
    entry = (
        next((e for e in found.entries if e.provider == provider), None)
        if found
        else None
    )
    if entry is not None:
        row["available_thinking_levels"] = {v: v for v in entry.thinking_levels} or None
        row["default_thinking_level"] = entry.default_thinking_level
        row["structured_output_mode"] = entry.default_structured_output_mode
    return row


OFFERED = Offered.from_payload(payload())
NOTHING_OFFERED = Offered.from_payload([])


def models_of(
    catalog: Catalog | None = None, offered: Offered = OFFERED, **args: Any
) -> ModelInfoList:
    if "tags" in args:
        args["tags"] = tuple(args["tags"])
    return list_models(
        build() if catalog is None else catalog,
        offered,
        SOURCES,
        ListModelsQuery(**args),
    )


def ids(answer: ModelInfoList) -> list[str]:
    return [row.model for row in answer.models]


def pairs(answer: ModelInfoList) -> dict[str, list[tuple[str, str]]]:
    return {
        row.model: [(p.provider, p.status) for p in row.providers]
        for row in answer.models
    }


def catalog_of(*models: tuple[str, str, int | None]) -> Catalog:
    """A catalogue of (model id, display name, featured rank), each on openai."""
    kiln = KilnModelList(
        models=tuple(
            KilnModel(
                name=name,
                friendly_name=display,
                family="f",
                featured_rank=rank,
                providers=[KilnModelProvider(name=ModelProviderName.openai)],
            )
            for name, display, rank in models
        ),
        providers=(),
        loaded_at=None,
    )
    return build_catalog(kiln, None)


def search(catalog: Catalog, text: str, **args: Any) -> ModelInfoList:
    return models_of(
        catalog, NOTHING_OFFERED, search=text, include_not_available=True, **args
    )


# ---- the status


def test_status_ready_not_offered_not_connected():
    assert status(OFFERED, "openai", "gpt_6_1_sol") == "ready"
    assert status(OFFERED, "openai", "claude_sonnet_5_5") == "not_offered"
    assert status(OFFERED, "vertex", "gemini_3_8_flash") == "not_connected"


@pytest.mark.parametrize(
    "bad",
    [None, {"provider_id": "openai"}, ["x", {"provider_id": 3}, {"models": []}]],
)
def test_offered_from_a_bad_payload_is_empty(bad):
    offered = Offered.from_payload(bad)
    assert offered.pairs == {} and offered.connected == frozenset()


def test_offered_skips_a_bad_model_and_keeps_the_provider_connected():
    offered = Offered.from_payload(
        [{"provider_id": "groq", "models": [{"name": "no id"}, "x", {"id": "k"}]}]
    )
    assert list(offered.pairs) == [("groq", "k")]
    assert offered.connected == {"groq"}


# ---- list_models


def test_list_models_returns_ready_entries_only_by_default():
    answer = models_of()
    assert answer.sources == SOURCES
    listed = pairs(answer)
    assert listed["gpt_6_1_sol"] == [("openai", "ready"), ("openrouter", "ready")]
    assert listed["claude_sonnet_5_5"] == [
        ("openrouter", "ready"),
        ("anthropic", "ready"),
    ]
    assert listed["gemini_3_8_flash"] == [("openrouter", "ready")]
    # Not offered: the typesafe model.
    assert "jev_1_13" not in listed
    assert all(s == "ready" for row in listed.values() for _, s in row)


def test_include_not_available_lists_every_status():
    listed = pairs(models_of(include_not_available=True))
    assert dict(listed["gemini_3_8_flash"]) == {
        "openrouter": "ready",
        "gemini_api": "not_connected",
        "vertex": "not_connected",
    }
    assert listed["jev_1_13"] == [("typesafe", "not_connected")]
    # OpenAI and TypeSafe connected, and the model not offered on TypeSafe.
    offered = Offered.from_payload(payload({"openai": ["gpt_6_1_sol"], "typesafe": []}))
    answer = models_of(offered=offered, include_not_available=True)
    assert pairs(answer)["jev_1_13"] == [("typesafe", "not_offered")]


def test_deprecated_entries_are_left_out_by_default():
    deprecated = Offered.from_payload(
        payload({"openrouter": ["glm_4_6"], "cerebras": ["glm_4_6"]})
    )
    assert pairs(models_of(offered=deprecated))["glm_4_6"] == [("openrouter", "ready")]
    row = models_of(offered=deprecated, include_deprecated=True).models[0]
    assert [(p.provider, p.deprecated) for p in row.providers] == [
        ("openrouter", False),
        ("cerebras", True),
    ]


def test_entry_filters_remove_entries_and_empty_rows():
    # openai's gpt entry has no tool calls in the fixture; openrouter's has.
    listed = pairs(models_of(supports_tools=True))
    assert listed["gpt_6_1_sol"] == [("openrouter", "ready")]
    assert pairs(models_of(supports_tools=False)) == {
        "gpt_6_1_sol": [("openai", "ready")]
    }
    # deepseek and glm have no vision: their rows go.
    assert set(pairs(models_of(supports_vision=False))) == {"deepseek_4_pro", "glm_4_6"}
    # qwen and glm have no thinking levels on openrouter.
    no_levels = models_of(has_thinking_levels=False)
    assert ids(no_levels) == ["qwen_3p8_max_0902", "glm_4_6"]
    assert no_levels.models[0].has_thinking_levels is False
    assert "glm_4_6" not in ids(models_of(has_thinking_levels=True))
    assert pairs(models_of(provider="openai")) == {"gpt_6_1_sol": [("openai", "ready")]}


def test_a_null_value_fails_a_filter_for_true_and_for_false():
    offered = Offered.from_payload(payload({}, openai={"id": "custom_x"}))
    # The payload-only model has no flag for tools: it passes neither filter.
    assert "custom_x" in ids(models_of(offered=offered))
    assert "custom_x" not in ids(models_of(offered=offered, supports_tools=True))
    assert "custom_x" not in ids(models_of(offered=offered, supports_tools=False))


def test_reasoning_model_is_a_row_filter_apart_from_thinking_levels():
    # qwen reasons (models.dev) and has no thinking level to set.
    (qwen,) = models_of(reasoning_model=True, has_thinking_levels=False).models
    assert (qwen.model, qwen.reasoning_model) == ("qwen_3p8_max_0902", True)
    # glm has no models.dev match: an unknown value does not pass.
    assert "glm_4_6" not in ids(models_of(reasoning_model=True))
    assert models_of(reasoning_model=False).models == []
    assert models_of().models[-1].reasoning_model is None


def with_medians(**medians: tuple[float | None, float | None]) -> Catalog:
    """The fixture catalogue with these (median input, median output)."""
    catalog = build()
    for model, (median_input, median_output) in medians.items():
        row = catalog.model(model)
        assert row is not None
        row.median_input_price, row.median_output_price = median_input, median_output
    return catalog


def test_sort_price_uses_the_median_before_the_entries():
    # gemini's median is 0.75 + 3.75 in the fixture. A median of 10 for
    # deepseek wins over its cheap openrouter entry (0.9 + 1.5).
    answer = models_of(catalog=with_medians(deepseek_4_pro=(5.0, 5.0)), sort="price")
    assert ids(answer) == [
        "gemini_3_8_flash",  # 4.5, the median
        "qwen_3p8_max_0902",  # 8, its entry
        "deepseek_4_pro",  # 10, the median
        "gpt_6_1_sol",  # 12
        "claude_sonnet_5_5",  # 12
        "glm_4_6",  # no price: last
    ]
    deepseek = answer.models[2]
    assert (deepseek.median_input_price, deepseek.median_output_price) == (5.0, 5.0)
    assert deepseek.providers[0].input_price == 0.9  # the entry is as listed
    # A median of one side only is not a median price: the entries decide.
    half = with_medians(deepseek_4_pro=(5.0, None))
    assert ids(models_of(catalog=half, sort="price"))[0] == "deepseek_4_pro"


def test_a_zero_price_is_shown_and_never_sorts():
    catalog = build()
    qwen = catalog.model("qwen_3p8_max_0902")
    assert qwen is not None
    qwen.entries[0].input_price = 0.0
    answer = models_of(catalog=catalog, sort="price")
    # No other price: qwen sorts with the unpriced rows, in the featured order.
    assert ids(answer)[-2:] == ["qwen_3p8_max_0902", "glm_4_6"]
    assert answer.models[-2].providers[0].input_price == 0.0


def test_row_filters_family_open_weights_and_tags():
    assert ids(models_of(family="claude")) == ["claude_sonnet_5_5"]
    assert ids(models_of(open_weights=True)) == ["deepseek_4_pro"]
    # glm's open weights are unknown: a filter on it leaves the row out.
    assert "glm_4_6" not in ids(models_of(open_weights=False))
    assert ids(models_of(tags=["strong_coding", "best_value"])) == [
        "gpt_6_1_sol",
        "deepseek_4_pro",
    ]
    assert ids(models_of(tags=["strong_agentic"], family="claude")) == [
        "claude_sonnet_5_5"
    ]


def test_a_tag_on_a_provider_entry_matches_the_row():
    assert pairs(models_of(tags=["fast"])) == {
        "gpt_6_1_sol": [("openai", "ready"), ("openrouter", "ready")]
    }
    # The tag is on the openai entry, which the provider filter removes.
    assert ids(models_of(tags=["fast"], provider="openrouter")) == []


def test_featured_true_and_false():
    assert ids(models_of(featured=True)) == [
        "gpt_6_1_sol",
        "qwen_3p8_max_0902",
        "deepseek_4_pro",
        "claude_sonnet_5_5",
        "gemini_3_8_flash",
    ]
    assert ids(models_of(featured=False)) == ["glm_4_6"]


def test_sort_featured_price_newest_and_ties():
    featured = [
        "gpt_6_1_sol",  # rank 4
        "qwen_3p8_max_0902",  # 6
        "deepseek_4_pro",  # 8
        "claude_sonnet_5_5",  # 10
        "gemini_3_8_flash",  # 12
        "glm_4_6",  # no rank: last
    ]
    assert ids(models_of()) == featured
    assert ids(models_of(sort="featured")) == featured
    assert ids(models_of(sort="price")) == [
        "deepseek_4_pro",  # 2.4
        "gemini_3_8_flash",  # 4.5
        "qwen_3p8_max_0902",  # 8
        "gpt_6_1_sol",  # 12, a tie: the featured order
        "claude_sonnet_5_5",  # 12
        "glm_4_6",  # no price: last
    ]
    assert ids(models_of(sort="newest")) == [
        "gpt_6_1_sol",  # 2026-09-29
        "claude_sonnet_5_5",  # 2026-09-28
        "qwen_3p8_max_0902",  # 2026-09-02, a tie: the featured order
        "gemini_3_8_flash",  # 2026-09-02
        "deepseek_4_pro",  # 2026-04-24
        "glm_4_6",  # 2025-09-30
    ]
    undated = models_of(sort="newest", include_not_available=True)
    assert ids(undated)[-1] == "jev_1_13"


def test_paging_and_total():
    page = models_of(limit=2, offset=1)
    assert page.total == 6
    assert ids(page) == ["qwen_3p8_max_0902", "deepseek_4_pro"]
    assert models_of(offset=10).models == [] and models_of(offset=10).total == 6


def test_include_notes():
    plain = models_of().models[0]
    assert (plain.editorial_notes, plain.agent_notes) == (None, None)
    noted = models_of(include_notes=True).models[0]
    assert noted.model == "gpt_6_1_sol"
    assert noted.editorial_notes and noted.agent_notes


def test_an_unknown_provider_is_refused():
    with pytest.raises(InvalidModelQueryError) as error:
        models_of(provider="google")
    message = str(error.value)
    assert message.startswith(
        "Unknown provider: google. Provider ids: amazon_bedrock, "
    )
    assert "gemini_api" in message and message.endswith(".")
    # A known provider with nothing listed is an empty answer, not an error.
    assert models_of(provider="groq").models == []


def test_a_pair_the_catalogue_lacks_is_listed_with_null_fields():
    offered = Offered.from_payload(
        payload(
            {},
            groq={
                "id": "qwen_3p8_max_0902",
                "name": "Qwen",
                "supports_function_calling": True,
                "available_thinking_levels": {"a": "low", "b": "high"},
            },
        )
    )
    (row,) = models_of(offered=offered).models
    assert row.model == "qwen_3p8_max_0902" and row.release_date == "2026-09-02"
    assert row.providers == [
        ModelInfoProviderEntryRow(
            provider="groq", status="ready", tags=[], deprecated=False
        )
    ]
    assert row.has_thinking_levels is True
    details = model_details(build(), offered, SOURCES, row.model, "groq")
    (entry,) = details.providers
    assert entry.thinking_levels == ["low", "high"]
    assert entry.supports_tools is True and entry.provider_model_id is None


def test_a_model_the_catalogue_lacks_is_listed_after_the_catalogue():
    fine_tune = {
        "id": FINE_TUNE,
        "name": "Moderator fine-tune",
        "supports_structured_output": True,
        "structured_output_mode": "json_schema",
        "suggested_for_evals": True,
        "untested_model": True,
    }
    offered = Offered.from_payload(
        payload(
            {"openrouter": ["glm_4_6"]},
            kiln_fine_tune=fine_tune,
            openai_compatible={"id": "aaa_custom", "name": "Custom"},
        )
    )
    answer = models_of(offered=offered)
    # After the catalogue's models, by model id.
    assert ids(answer) == ["glm_4_6", FINE_TUNE, "aaa_custom"]
    row = answer.models[ids(answer).index(FINE_TUNE)]
    assert row.display_name == "Moderator fine-tune"
    assert (row.family, row.kiln_featured_rank, row.release_date) == (None, None, None)
    assert row.providers[0].provider == "kiln_fine_tune"
    assert row.providers[0].input_price is None
    (entry,) = model_details(build(), offered, SOURCES, FINE_TUNE, None).providers
    assert entry.default_structured_output_mode == "json_schema"
    assert entry.kiln_suggested_for == ["eval_judge"] and entry.untested is True
    assert entry.supports_tools is None


def test_the_offered_values_win_for_an_offered_pair():
    # Kiln runs with another model list version: other thinking levels and
    # another output mode for gpt on openai. Code checks the levels against
    # the payload, so the answers give the payload's.
    offered = Offered.from_payload(
        payload(
            {"openrouter": ["gpt_6_1_sol"]},
            openai={
                "id": "gpt_6_1_sol",
                "available_thinking_levels": {"x": "low", "y": "xhigh"},
                "default_thinking_level": "xhigh",
                "structured_output_mode": "json_mode",
            },
        )
    )
    details = model_details(CATALOG, offered, SOURCES, "gpt_6_1_sol", None)
    entries = {e.provider: e for e in details.providers}
    assert entries["openai"].thinking_levels == ["low", "xhigh"]
    assert entries["openai"].default_thinking_level == "xhigh"
    assert entries["openai"].default_structured_output_mode == "json_mode"
    # The catalogue's other fields stay, and the catalogue is not changed.
    assert entries["openai"].input_price == 2.0
    assert entries["openai"].provider_model_id == "gpt-6.1-sol"
    gpt = CATALOG.model("gpt_6_1_sol")
    assert gpt is not None
    (catalogue_entry,) = [e for e in gpt.entries if e.provider == "openai"]
    assert catalogue_entry.thinking_levels == ["none", "low", "medium", "high"]
    # A payload with no thinking levels for the pair: none are listed.
    offered = Offered.from_payload(payload({}, openai={"id": "gpt_6_1_sol"}))
    (entry,) = model_details(
        CATALOG, offered, SOURCES, "gpt_6_1_sol", "openai"
    ).providers
    assert entry.thinking_levels == [] and entry.default_structured_output_mode is None


def test_no_models_dev_data_gives_kiln_rows_with_null_prices():
    answer = models_of(catalog=build_catalog(kiln_list(), None))
    assert ids(answer) == ids(models_of())
    assert all(row.median_input_price is None for row in answer.models)
    assert all(p.input_price is None for row in answer.models for p in row.providers)
    assert all(row.release_date is None for row in answer.models)
    assert answer.models[0].kiln_featured_rank == 4


# ---- search


def test_search_ranks_exact_prefix_substring_then_words():
    catalog = catalog_of(
        ("mini_gpt_5_turbo", "Mini GPT 5 Turbo", None),  # every word
        ("old_gpt_5_mini", "Old GPT 5 Mini", None),  # substring
        ("gpt_5_mini_high", "GPT 5 Mini High", None),  # prefix
        ("gpt_5_mini", "GPT-5 Mini", None),  # exact
        ("claude", "Claude", 1),
    )
    answer = search(catalog, "GPT 5 mini")
    assert ids(answer) == [
        "gpt_5_mini",
        "gpt_5_mini_high",
        "old_gpt_5_mini",
        "mini_gpt_5_turbo",
    ]
    assert answer.total == 4 and answer.fuzzy_match is False
    # The display name counts as much as the id.
    assert ids(search(catalog, "Old GPT 5 Mini"))[0] == "old_gpt_5_mini"


def test_search_ties_keep_the_featured_order():
    catalog = catalog_of(
        ("gpt_x_low", "GPT X Low", None),
        ("gpt_x_mid", "GPT X Mid", 2),
        ("gpt_x_top", "GPT X Top", 1),
    )
    assert ids(search(catalog, "gpt x")) == ["gpt_x_top", "gpt_x_mid", "gpt_x_low"]


def test_an_explicit_sort_with_search_ignores_the_match_rank():
    catalog = catalog_of(
        ("gpt_5_mini", "GPT-5 Mini", 3),
        ("old_gpt_5_mini", "Old GPT 5 Mini", 1),
    )
    assert ids(search(catalog, "gpt 5 mini")) == ["gpt_5_mini", "old_gpt_5_mini"]
    assert ids(search(catalog, "gpt 5 mini", sort="featured")) == [
        "old_gpt_5_mini",
        "gpt_5_mini",
    ]


def test_the_typo_pass_sets_fuzzy_match():
    catalog = catalog_of(("gpt_5_mini", "GPT-5 Mini", None), ("claude", "Claude", 1))
    answer = search(catalog, "gpt 5 mimi")
    assert ids(answer) == ["gpt_5_mini"] and answer.fuzzy_match is True


def test_a_search_with_no_match_is_empty():
    answer = models_of(search="nova", include_not_available=True)
    assert answer.models == [] and answer.total == 0 and answer.fuzzy_match is False


def test_the_search_runs_after_the_other_filters():
    assert ids(models_of(search="jev")) == []
    assert ids(models_of(search="jev", include_not_available=True)) == ["jev_1_13"]


@pytest.mark.parametrize("text", ["--", " ", "::/"])
def test_a_search_with_no_letter_or_digit_is_refused(text):
    with pytest.raises(InvalidModelQueryError, match="at least one letter or digit"):
        models_of(search=text)
    with pytest.raises(InvalidModelQueryError):
        search_rows(text, [])


# ---- model_details


def test_model_details_lists_every_entry_with_its_status():
    details = model_details(build(), OFFERED, SOURCES, "deepseek_4_pro", None)
    assert details.sources == SOURCES
    assert details.display_name == "DeepSeek V4 Pro"
    assert details.release_date_estimated is False and details.open_weights is True
    assert [(p.provider, p.status, p.deprecated) for p in details.providers] == [
        ("openrouter", "ready", False),
        ("fireworks_ai", "not_connected", True),
        ("together_ai", "not_connected", True),
        ("featherless_ai", "not_connected", False),
        ("siliconflow_cn", "not_connected", False),
        ("cloudflare", "not_connected", False),
    ]
    openrouter = details.providers[0]
    assert (openrouter.input_price, openrouter.output_price) == (0.9, 1.5)
    assert openrouter.provider_model_id == "deepseek/deepseek-v4-pro"
    gpt = model_details(build(), OFFERED, SOURCES, "gpt_6_1_sol", None)
    assert gpt.agent_notes and gpt.editorial_notes and gpt.has_thinking_levels is True


def test_model_details_with_a_provider_keeps_one_entry():
    details = model_details(build(), OFFERED, SOURCES, "claude_sonnet_5_5", "anthropic")
    assert [(p.provider, p.status) for p in details.providers] == [
        ("anthropic", "ready")
    ]
    with pytest.raises(ModelNotFoundError) as error:
        model_details(build(), OFFERED, SOURCES, "claude_sonnet_5_5", "groq")
    assert str(error.value) == (
        "Model claude_sonnet_5_5 has no entry for provider groq."
        " Its providers: openrouter, anthropic."
    )


def test_model_details_lookup_forgives_case_when_it_is_unique():
    details = model_details(build(), OFFERED, SOURCES, "GPT_6_1_SOL", None)
    assert details.model == "gpt_6_1_sol"
    offered = Offered.from_payload(
        payload(
            {},
            openai_compatible={"id": "Server::Model"},
            ollama={"id": "server::model"},
        )
    )
    assert model_details(build(), offered, SOURCES, "Server::Model", None).model == (
        "Server::Model"
    )
    with pytest.raises(ModelNotFoundError, match=r"^Model not found: SERVER::MODEL\."):
        model_details(build(), offered, SOURCES, "SERVER::MODEL", None)


def test_model_details_names_the_closest_ids():
    with pytest.raises(ModelNotFoundError) as error:
        model_details(build(), OFFERED, SOURCES, "gpt_6_1_sl", None)
    assert str(error.value) == (
        "Model not found: gpt_6_1_sl. Closest ids: gpt_6_1_sol. To find a model id,"
        " call GET /api/model_info/models with search=<name> and"
        " include_not_available=true."
    )
    with pytest.raises(ModelNotFoundError) as error:
        model_details(build(), OFFERED, SOURCES, "::", None)
    assert str(error.value).startswith("Model not found: ::. To find a model id,")
    with pytest.raises(ModelNotFoundError) as error:
        model_details(build(), OFFERED, SOURCES, "gpt", None)
    assert "Closest ids: gpt_6_1_sol." in str(error.value)


# ---- list_providers


def test_list_providers_counts_ready_models_and_orders_them():
    answer = list_providers(build(), OFFERED, SOURCES)
    assert answer.sources == SOURCES
    rows = [(p.provider, p.status, p.ready_model_count) for p in answer.providers]
    assert rows[:3] == [
        ("openrouter", "connected", 6),
        ("anthropic", "connected", 1),
        ("openai", "connected", 1),
    ]
    assert all(
        status == "not_connected" and count == 0 for _, status, count in rows[3:]
    )
    assert [r[0] for r in rows[3:]] == sorted(r[0] for r in rows[3:])
    openai = answer.providers[2]
    assert openai.name == "OpenAI" and openai.notes


def test_list_providers_lists_unconnected_providers():
    rows = {p.provider: p for p in list_providers(build(), OFFERED, SOURCES).providers}
    # Kiln's providers, the providers of the entries, and the connected ones.
    assert {"typesafe", "cloudflare", "vertex", "cerebras", "ollama"} <= set(rows)
    assert rows["cloudflare"].status == "not_connected"
    assert rows["cloudflare"].name == "Cloudflare Workers AI"
    assert rows["typesafe"].ready_model_count == 0
    offered = Offered.from_payload(payload({}, a_server={"id": "x"}))
    unknown = list_providers(build(), offered, SOURCES).providers[0]
    assert (unknown.provider, unknown.status, unknown.name) == (
        "a_server",
        "connected",
        None,
    )
