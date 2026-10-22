#!/usr/bin/env python3
"""Check Kiln's Cloudflare thinking levels against Cloudflare's model catalog.

Cloudflare publishes, per model, the `reasoning_effort` values it accepts
(`reasoning_effort.supported_efforts`) and the values it silently remaps to a
different effort (`reasoning_effort.normalizes_to`). A remapped value still
returns HTTP 200, so a live call cannot catch it; only the catalog shows it.

Reads the model list from this checkout (not the published remote config), so
it checks the branch being edited. Run from the repo root:

    uv run python .agents/skills/claude-maintain-models/scripts/check_cloudflare_thinking_levels.py

Uses the authenticated models-search API when CLOUDFLARE_API_KEY and
CLOUDFLARE_ACCOUNT_ID are both set, and otherwise the public catalog JSON.

Exit code 1 when any entry has an error-level finding, else 0.
"""

from __future__ import annotations

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
    cloudflare_property,
    fetch_cloudflare_models,
    log,
)

ERROR_KINDS = {
    "missing_levels",
    "unsupported_level",
    "unsupported_default",
    "levels_without_catalog_efforts",
    "not_in_catalog",
}


@dataclass(frozen=True)
class KilnCloudflareEntry:
    model_name: str
    model_id: str
    levels: dict[str, str] | None
    default_level: str | None


@dataclass(frozen=True)
class Finding:
    kind: str
    model_name: str
    model_id: str
    detail: str

    @property
    def is_error(self) -> bool:
        return self.kind in ERROR_KINDS


def _reasoning_effort(model: dict) -> dict[str, Any]:
    value = cloudflare_property(model, "reasoning_effort")
    if isinstance(value, str):
        # The authenticated search API returns property values as JSON strings.
        try:
            value = json.loads(value)
        except ValueError:
            return {}
    return value if isinstance(value, dict) else {}


def check_entry(
    entry: KilnCloudflareEntry, catalog_model: dict | None
) -> list[Finding]:
    """Compare one Kiln Cloudflare entry with its catalog record."""

    def finding(kind: str, detail: str) -> Finding:
        return Finding(kind, entry.model_name, entry.model_id, detail)

    if catalog_model is None:
        return [finding("not_in_catalog", "no text-generation model with this id")]

    effort = _reasoning_effort(catalog_model)
    supported: list[str] = effort.get("supported_efforts") or []
    remaps: dict[str, str] = effort.get("normalizes_to") or {}
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

    if not offered:
        return [
            finding(
                "missing_levels",
                f"catalog supports {supported} (default "
                f"{effort.get('default_effort')!r}); entry has no thinking levels",
            )
        ]

    findings: list[Finding] = []
    for value in offered:
        if value not in supported:
            remap = remaps.get(value)
            target = f"; Cloudflare runs it as {remap!r}" if remap else ""
            findings.append(
                finding(
                    "unsupported_level",
                    f"{value!r} is not in supported_efforts {supported}{target}",
                )
            )
    if entry.default_level is not None and entry.default_level not in supported:
        findings.append(
            finding(
                "unsupported_default",
                f"default {entry.default_level!r} is not in supported_efforts {supported}",
            )
        )
    not_offered = [value for value in supported if value not in offered]
    if not_offered:
        findings.append(
            finding("not_offered", f"supported but not offered: {not_offered}")
        )
    return findings


def check_all(entries: list[KilnCloudflareEntry], catalog: list[dict]) -> list[Finding]:
    by_name = {
        model["name"]: model
        for model in catalog
        if (model.get("task") or {}).get("name") == CLOUDFLARE_TEXT_GENERATION_TASK
    }
    findings: list[Finding] = []
    for entry in entries:
        findings.extend(check_entry(entry, by_name.get(entry.model_id)))
    return findings


def load_kiln_entries() -> list[KilnCloudflareEntry]:
    from kiln_ai.adapters.ml_model_list import built_in_models
    from kiln_ai.datamodel.datamodel_enums import ModelProviderName

    return [
        KilnCloudflareEntry(
            model_name=model.name,
            model_id=provider.model_id,
            levels=provider.available_thinking_levels,
            default_level=provider.default_thinking_level,
        )
        for model in built_in_models
        for provider in model.providers
        if provider.name == ModelProviderName.cloudflare
        and provider.model_id
        and not provider.deprecated
    ]


def main() -> int:
    entries = load_kiln_entries()
    catalog = fetch_cloudflare_models(
        os.environ.get("CLOUDFLARE_API_KEY"), os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    )
    findings = check_all(entries, catalog)

    log(f"Checked {len(entries)} Cloudflare entries")
    for item in findings:
        marker = "❌" if item.is_error else "note:"
        log(
            f"  {marker} {item.kind}: {item.model_name} ({item.model_id}): {item.detail}"
        )
    if not findings:
        log("  ✅ every entry matches the catalog")

    json.dump([asdict(item) for item in findings], sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 1 if any(item.is_error for item in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
