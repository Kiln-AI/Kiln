#!/usr/bin/env python3
"""Check Kiln's thinking levels against the provider's published effort lists.

Cloudflare and OpenRouter publish, per model, the `reasoning_effort` values
the model accepts (`supported_efforts`). Both silently map an unlisted value
to a different effort and still return HTTP 200, so a live call cannot catch
a wrong level; only the catalog shows it. Cloudflare also lists the exact
mapping (`normalizes_to`).

Reads the model list from this checkout (not the published remote config), so
it checks the branch being edited. Run from the repo root:

    uv run python .agents/skills/claude-maintain-models/scripts/check_thinking_levels.py
    uv run python .agents/skills/claude-maintain-models/scripts/check_thinking_levels.py --provider cloudflare

Cloudflare uses the authenticated models-search API when CLOUDFLARE_API_KEY and
CLOUDFLARE_ACCOUNT_ID are both set, and otherwise the public catalog JSON.
OpenRouter needs no key.

Exit code 1 when any entry has an error-level finding, else 0.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

# Script is at .agents/skills/<skill>/scripts/<file>.py
# parent chain: scripts -> <skill> -> skills -> .agents
sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent.parent.parent / "scripts")
)

from provider_utils import (  # type: ignore[import-not-found]
    CLOUDFLARE_TEXT_GENERATION_TASK,
    OPENROUTER_VIRTUAL_SUFFIXES,
    cloudflare_property,
    fetch_cloudflare_models,
    fetch_openrouter_models,
    log,
)

PROVIDERS = ("cloudflare", "openrouter")

# Kinds that are always errors. `missing_levels`, `levels_without_catalog_efforts`
# and `not_in_catalog` are errors only for providers in STRICT_PROVIDERS.
ERROR_KINDS = {"unsupported_level", "unsupported_default"}
STRICT_KINDS = {"missing_levels", "levels_without_catalog_efforts", "not_in_catalog"}
# Kiln leaves OpenRouter levels off some models on purpose (an effort value
# with no visible effect), and other Kiln checks cover OpenRouter ids, so only
# Cloudflare treats those kinds as errors.
STRICT_PROVIDERS = {"cloudflare"}


@dataclass(frozen=True)
class KilnEntry:
    provider: str
    model_name: str
    model_id: str
    levels: dict[str, str] | None
    default_level: str | None


@dataclass(frozen=True)
class CatalogEffort:
    """A model's effort data from the provider's catalog.

    `supported` is None when the catalog does not list efforts for the model,
    and `accepts_any` is True when the provider says every effort is accepted.
    """

    supported: list[str] | None
    default: str | None = None
    remaps: dict[str, str] | None = None
    accepts_any: bool = False


@dataclass(frozen=True)
class Finding:
    kind: str
    provider: str
    model_name: str
    model_id: str
    detail: str

    @property
    def is_error(self) -> bool:
        if self.kind in ERROR_KINDS:
            return True
        return self.kind in STRICT_KINDS and self.provider in STRICT_PROVIDERS


def check_entry(entry: KilnEntry, effort: CatalogEffort | None) -> list[Finding]:
    """Compare one Kiln provider entry with its catalog effort data.

    `effort` is None when the model is not in the catalog.
    """

    def finding(kind: str, detail: str) -> Finding:
        return Finding(kind, entry.provider, entry.model_name, entry.model_id, detail)

    if effort is None:
        return [finding("not_in_catalog", "the catalog has no model with this id")]
    if effort.accepts_any:
        return []

    supported = effort.supported or []
    offered = list((entry.levels or {}).values())

    if not supported:
        if offered:
            return [
                finding(
                    "levels_without_catalog_efforts",
                    f"entry offers {offered}, but the catalog lists no supported_efforts",
                )
            ]
        return []

    findings: list[Finding] = []
    if entry.default_level is not None and entry.default_level not in supported:
        findings.append(
            finding(
                "unsupported_default",
                f"default {entry.default_level!r} is not in supported_efforts {supported}",
            )
        )
    if not offered:
        findings.append(
            finding(
                "missing_levels",
                f"catalog supports {supported} (default {effort.default!r}); "
                "entry has no thinking levels",
            )
        )
        return findings

    remaps = effort.remaps or {}
    for value in offered:
        if value not in supported:
            remap = remaps.get(value)
            target = f"; the provider runs it as {remap!r}" if remap else ""
            findings.append(
                finding(
                    "unsupported_level",
                    f"{value!r} is not in supported_efforts {supported}{target}",
                )
            )
    not_offered = [value for value in supported if value not in offered]
    if not_offered:
        findings.append(
            finding("not_offered", f"supported but not offered: {not_offered}")
        )
    return findings


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        # The Cloudflare search API returns property values as JSON strings.
        try:
            value = json.loads(value)
        except ValueError:
            return {}
    return value if isinstance(value, dict) else {}


def cloudflare_efforts(catalog: list[dict]) -> dict[str, CatalogEffort]:
    efforts: dict[str, CatalogEffort] = {}
    for model in catalog:
        if (model.get("task") or {}).get("name") != CLOUDFLARE_TEXT_GENERATION_TASK:
            continue
        effort = _as_dict(cloudflare_property(model, "reasoning_effort"))
        efforts[model["name"]] = CatalogEffort(
            supported=effort.get("supported_efforts") or None,
            default=effort.get("default_effort"),
            remaps=effort.get("normalizes_to"),
        )
    return efforts


def openrouter_efforts(catalog: list[dict]) -> dict[str, CatalogEffort]:
    efforts: dict[str, CatalogEffort] = {}
    for model in catalog:
        reasoning = model.get("reasoning")
        if not isinstance(reasoning, dict):
            efforts[model["id"]] = CatalogEffort(supported=None)
            continue
        supported = reasoning.get("supported_efforts")
        efforts[model["id"]] = CatalogEffort(
            supported=supported or None,
            default=reasoning.get("default_effort"),
            # OpenRouter documents a null list as "every gateway effort is accepted".
            accepts_any="supported_efforts" in reasoning and supported is None,
        )
    return efforts


def catalog_id(provider: str, model_id: str) -> str:
    if provider == "openrouter":
        for suffix in OPENROUTER_VIRTUAL_SUFFIXES:
            model_id = model_id.removesuffix(suffix)
    return model_id


def check_all(
    entries: list[KilnEntry], efforts_by_provider: dict[str, dict[str, CatalogEffort]]
) -> list[Finding]:
    findings: list[Finding] = []
    for entry in entries:
        efforts = efforts_by_provider[entry.provider]
        findings.extend(
            check_entry(entry, efforts.get(catalog_id(entry.provider, entry.model_id)))
        )
    return findings


def load_kiln_entries(providers: list[str]) -> list[KilnEntry]:
    from kiln_ai.adapters.ml_model_list import built_in_models

    return [
        KilnEntry(
            provider=provider.name.value,
            model_name=model.name,
            model_id=provider.model_id,
            levels=provider.available_thinking_levels,
            default_level=provider.default_thinking_level,
        )
        for model in built_in_models
        for provider in model.providers
        if provider.name.value in providers
        and provider.model_id
        and not provider.deprecated
    ]


def fetch_efforts(provider: str) -> dict[str, CatalogEffort]:
    if provider == "cloudflare":
        return cloudflare_efforts(
            fetch_cloudflare_models(
                os.environ.get("CLOUDFLARE_API_KEY"),
                os.environ.get("CLOUDFLARE_ACCOUNT_ID"),
            )
        )
    return openrouter_efforts(fetch_openrouter_models())


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check Kiln's thinking levels against provider effort lists."
    )
    parser.add_argument(
        "--provider",
        choices=[*PROVIDERS, "all"],
        default="all",
        help="Provider to check (default: all)",
    )
    args = parser.parse_args()
    providers = list(PROVIDERS) if args.provider == "all" else [args.provider]

    entries = load_kiln_entries(providers)
    findings = check_all(entries, {p: fetch_efforts(p) for p in providers})

    for provider in providers:
        count = sum(1 for entry in entries if entry.provider == provider)
        log(f"Checked {count} {provider} entries")
        provider_findings = [f for f in findings if f.provider == provider]
        for item in provider_findings:
            marker = "❌" if item.is_error else "note:"
            log(
                f"  {marker} {item.kind}: {item.model_name} ({item.model_id}): {item.detail}"
            )
        if not any(item.is_error for item in provider_findings):
            log("  ✅ no errors")

    json.dump([asdict(item) for item in findings], sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 1 if any(item.is_error for item in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
