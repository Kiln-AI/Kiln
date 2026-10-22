import json

import pytest
from check_thinking_levels import (
    CatalogEffort,
    KilnEntry,
    check_all,
    check_entry,
    cloudflare_efforts,
    openrouter_efforts,
)

GLM_5_3 = CatalogEffort(
    supported=["max", "high", "low"],
    default="max",
    remaps={"medium": "max", "none": "max"},
)


def entry(
    levels: dict[str, str] | None,
    default: str | None = None,
    provider: str = "cloudflare",
    model_id: str = "@cf/zai-org/glm-5.3",
) -> KilnEntry:
    return KilnEntry(
        provider=provider,
        model_name="glm_5_3",
        model_id=model_id,
        levels=levels,
        default_level=default,
    )


def kinds(findings) -> list[str]:
    return [item.kind for item in findings]


def test_missing_levels_is_an_error_on_cloudflare_only():
    cf = check_entry(entry(None), GLM_5_3)
    assert kinds(cf) == ["missing_levels"]
    assert cf[0].is_error

    orr = check_entry(entry(None, provider="openrouter"), GLM_5_3)
    assert kinds(orr) == ["missing_levels"]
    assert not orr[0].is_error


def test_remapped_level_is_an_error_and_names_the_target():
    levels = {"Low": "low", "Medium": "medium", "High": "high"}
    findings = check_entry(entry(levels, "high"), GLM_5_3)
    assert kinds(findings) == ["unsupported_level", "not_offered"]
    assert findings[0].is_error
    assert "'max'" in findings[0].detail


def test_unlisted_level_is_an_error_on_openrouter():
    levels = {"Minimal": "minimal", "Low": "low"}
    effort = CatalogEffort(supported=["low", "high"])
    findings = check_entry(entry(levels, "low", provider="openrouter"), effort)
    assert kinds(findings) == ["unsupported_level", "not_offered"]
    assert findings[0].is_error


def test_unsupported_default_is_an_error():
    levels = {"Low": "low", "High": "high", "Max": "max"}
    findings = check_entry(entry(levels, "medium"), GLM_5_3)
    assert kinds(findings) == ["unsupported_default"]
    assert findings[0].is_error


def test_exact_match_has_no_findings():
    levels = {"Low": "low", "High": "high", "Max": "max"}
    assert check_entry(entry(levels, "max"), GLM_5_3) == []


def test_unoffered_effort_is_a_note():
    findings = check_entry(entry({"Low": "low", "High": "high"}, "high"), GLM_5_3)
    assert kinds(findings) == ["not_offered"]
    assert not findings[0].is_error


@pytest.mark.parametrize(
    "provider,is_error", [("cloudflare", True), ("openrouter", False)]
)
def test_levels_without_catalog_efforts(provider, is_error):
    no_list = CatalogEffort(supported=None)
    assert check_entry(entry(None, provider=provider), no_list) == []
    findings = check_entry(entry({"High": "high"}, provider=provider), no_list)
    assert kinds(findings) == ["levels_without_catalog_efforts"]
    assert findings[0].is_error is is_error


def test_accepts_any_has_no_findings():
    anything = CatalogEffort(supported=None, accepts_any=True)
    assert check_entry(entry({"Wild": "wild"}, provider="openrouter"), anything) == []


def test_cloudflare_efforts_parses_dicts_and_json_strings():
    catalog = [
        {
            "name": "@cf/a",
            "task": {"name": "Text Generation"},
            "properties": [
                {
                    "property_id": "reasoning_effort",
                    "value": {"supported_efforts": ["high"], "default_effort": "high"},
                }
            ],
        },
        {
            "name": "@cf/b",
            "task": {"name": "Text Generation"},
            "properties": [
                {
                    "property_id": "reasoning_effort",
                    "value": json.dumps(
                        {"supported_efforts": ["low"]}, ensure_ascii=False
                    ),
                }
            ],
        },
        {"name": "@cf/embed", "task": {"name": "Text Embeddings"}, "properties": []},
    ]
    efforts = cloudflare_efforts(catalog)
    assert efforts["@cf/a"].supported == ["high"]
    assert efforts["@cf/a"].default == "high"
    assert efforts["@cf/b"].supported == ["low"]
    assert "@cf/embed" not in efforts


def test_openrouter_efforts_reads_the_reasoning_object():
    catalog = [
        {"id": "a/listed", "reasoning": {"supported_efforts": ["high", "low"]}},
        {"id": "a/any", "reasoning": {"supported_efforts": None}},
        {"id": "a/none"},
    ]
    efforts = openrouter_efforts(catalog)
    assert efforts["a/listed"].supported == ["high", "low"]
    assert efforts["a/any"].accepts_any
    assert efforts["a/none"].supported is None
    assert not efforts["a/none"].accepts_any


def test_check_all_strips_openrouter_virtual_suffix():
    efforts = {"openrouter": {"z-ai/glm-5.3": GLM_5_3}}
    exacto = entry(None, provider="openrouter", model_id="z-ai/glm-5.3:exacto")
    assert kinds(check_all([exacto], efforts)) == ["missing_levels"]

    missing = entry(None, provider="openrouter", model_id="z-ai/unknown")
    assert kinds(check_all([missing], efforts)) == ["not_in_catalog"]


def test_unsupported_default_is_reported_when_levels_are_missing():
    findings = check_entry(entry(None, "medium", provider="openrouter"), GLM_5_3)
    assert kinds(findings) == ["unsupported_default", "missing_levels"]
    assert findings[0].is_error
    assert not findings[1].is_error
