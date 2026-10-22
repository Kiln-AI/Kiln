import json

import pytest
from check_cloudflare_thinking_levels import (
    KilnCloudflareEntry,
    check_all,
    check_entry,
)

GLM_5_3_EFFORT = {
    "supported_efforts": ["max", "high", "low"],
    "default_effort": "max",
    "normalizes_to": {"medium": "max", "none": "max"},
    "mandatory": True,
}


def catalog_model(name: str, effort: dict | None) -> dict:
    properties = [{"property_id": "reasoning", "value": "true"}]
    if effort is not None:
        properties.append({"property_id": "reasoning_effort", "value": effort})
    return {
        "name": name,
        "task": {"name": "Text Generation"},
        "properties": properties,
    }


def entry(levels: dict[str, str] | None, default: str | None = None):
    return KilnCloudflareEntry(
        model_name="glm_5_3",
        model_id="@cf/zai-org/glm-5.3",
        levels=levels,
        default_level=default,
    )


def kinds(findings) -> list[str]:
    return [item.kind for item in findings]


def test_missing_levels_when_catalog_lists_efforts():
    findings = check_entry(entry(None), catalog_model("x", GLM_5_3_EFFORT))
    assert kinds(findings) == ["missing_levels"]
    assert findings[0].is_error


def test_remapped_level_is_an_error_and_names_the_target():
    levels = {"Low": "low", "Medium": "medium", "High": "high"}
    findings = check_entry(entry(levels, "high"), catalog_model("x", GLM_5_3_EFFORT))
    assert kinds(findings) == ["unsupported_level", "not_offered"]
    assert "'max'" in findings[0].detail


def test_unsupported_default_is_an_error():
    levels = {"Low": "low", "High": "high", "Max": "max"}
    findings = check_entry(entry(levels, "medium"), catalog_model("x", GLM_5_3_EFFORT))
    assert kinds(findings) == ["unsupported_default"]


def test_exact_match_has_no_findings():
    levels = {"Low": "low", "High": "high", "Max": "max"}
    findings = check_entry(entry(levels, "max"), catalog_model("x", GLM_5_3_EFFORT))
    assert findings == []


def test_unoffered_effort_is_informational():
    levels = {"Low": "low", "High": "high"}
    findings = check_entry(entry(levels, "high"), catalog_model("x", GLM_5_3_EFFORT))
    assert kinds(findings) == ["not_offered"]
    assert not findings[0].is_error


@pytest.mark.parametrize("effort", [None, {"mandatory": False}])
def test_no_catalog_efforts(effort):
    assert check_entry(entry(None), catalog_model("x", effort)) == []
    findings = check_entry(entry({"High": "high"}), catalog_model("x", effort))
    assert kinds(findings) == ["levels_without_catalog_efforts"]


def test_search_api_json_string_values_are_parsed():
    model = catalog_model("x", None)
    model["properties"].append(
        {"property_id": "reasoning_effort", "value": json.dumps(GLM_5_3_EFFORT)}
    )
    assert kinds(check_entry(entry(None), model)) == ["missing_levels"]


def test_check_all_matches_by_id_and_skips_other_tasks():
    embedding = {"name": "@cf/zai-org/glm-5.3", "task": {"name": "Text Embeddings"}}
    findings = check_all([entry(None)], [embedding])
    assert kinds(findings) == ["not_in_catalog"]

    model = catalog_model("@cf/zai-org/glm-5.3", GLM_5_3_EFFORT)
    assert kinds(check_all([entry(None)], [model])) == ["missing_levels"]
