#!/usr/bin/env python3
"""Check fine-tunable model availability across providers.

Two modes:
  - "static"    — checks provider_finetune_id entries in ml_model_list.py
  - "fireworks" — cross-references Fireworks API tunable models against their docs
  - "all"       — runs both checks

Usage:
    python3 .agents/skills/kiln-check-finetune-deprecation/scripts/check_finetune.py static
    python3 .agents/skills/kiln-check-finetune-deprecation/scripts/check_finetune.py fireworks
    python3 .agents/skills/kiln-check-finetune-deprecation/scripts/check_finetune.py all

Requires:
    - API keys set as environment variables (source .env first)
    - required_permissions: ["all"] when run via sandbox (network access needed)
"""

import argparse
import json
import sys
from pathlib import Path

# Add shared scripts directory and repo root to path so we can import from
# provider_utils.py and kiln_ai.adapters.fine_tune.fireworks_finetune
# Script is at .agents/skills/<skill>/scripts/<file>.py
# parent chain: scripts -> <skill> -> skills -> .agents
sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent.parent.parent / "scripts")
)

from provider_utils import (  # type: ignore[import-not-found]
    fetch_fireworks_docs_models,
    fetch_fireworks_tunable,
    fetch_together_docs_models,
    fetch_vertex_with_aliases,
    find_repo_root,
    get_api_key,
    log,
)

REPO_ROOT = find_repo_root()
sys.path.insert(0, str(REPO_ROOT / "libs" / "core"))

from kiln_ai.adapters.fine_tune.fireworks_finetune import (  # noqa: E402  # type: ignore[import-not-found]
    FIREWORKS_SUPPORTED_FINETUNE_MODELS,
)
from kiln_ai.adapters.ml_model_list import (  # noqa: E402  # type: ignore[import-not-found]
    built_in_models,
)

FIREWORKS_MODEL_PREFIX = "accounts/fireworks/models/"


# ---------------------------------------------------------------------------
# Extract static provider_finetune_id entries from the model list
# ---------------------------------------------------------------------------


def extract_static_finetune_ids() -> list[dict]:
    """Extract all provider_finetune_id entries from built_in_models.

    Returns list of {model_name, provider, finetune_id} dicts.
    """
    entries: list[dict] = []

    for model in built_in_models:
        for provider in model.providers:
            if provider.provider_finetune_id:
                entries.append(
                    {
                        "model_name": model.friendly_name,
                        "provider": provider.name.value,
                        "finetune_id": provider.provider_finetune_id,
                    }
                )

    return entries


# ---------------------------------------------------------------------------
# Check static providers
# ---------------------------------------------------------------------------


def check_together_finetune(finetune_ids: list[str]) -> dict:
    """Check Together fine-tune IDs against the Together docs page.

    The /v1/models API only lists inference models, not fine-tuning Reference
    models. The docs page is the source of truth for fine-tuning support.
    """
    try:
        docs_models = fetch_together_docs_models()
    except (RuntimeError, OSError) as e:
        return {
            "skipped": True,
            "reason": f"Could not scrape Together docs: {type(e).__name__}",
        }

    found = [fid for fid in finetune_ids if fid in docs_models]
    missing = [fid for fid in finetune_ids if fid not in docs_models]
    return {"found": found, "missing": missing, "available_count": len(docs_models)}


def check_vertex_finetune(finetune_ids: list[str]) -> dict:
    project_id = get_api_key("VERTEX_PROJECT_ID")
    if not project_id:
        return {"skipped": True, "reason": "VERTEX_PROJECT_ID not set"}

    try:
        available = fetch_vertex_with_aliases(project_id)
    except (RuntimeError, FileNotFoundError) as e:
        return {"skipped": True, "reason": f"Vertex API error: {type(e).__name__}"}

    found = [fid for fid in finetune_ids if fid in available]
    missing = [fid for fid in finetune_ids if fid not in available]
    return {"found": found, "missing": missing, "available_count": len(available)}


def check_static() -> dict:
    entries = extract_static_finetune_ids()
    log(f"Found {len(entries)} static provider_finetune_id entries")

    by_provider: dict[str, list[str]] = {}
    entry_map: dict[str, list[dict]] = {}
    for e in entries:
        provider = e["provider"]
        if provider not in by_provider:
            by_provider[provider] = []
            entry_map[provider] = []
        by_provider[provider].append(e["finetune_id"])
        entry_map[provider].append(e)

    results: dict[str, dict] = {}
    checkers = {
        "together_ai": check_together_finetune,
        "vertex": check_vertex_finetune,
    }

    for provider, finetune_ids in by_provider.items():
        log(f"  Checking {provider} ({len(finetune_ids)} models)...")
        checker = checkers.get(provider)
        if not checker:
            results[provider] = {
                "skipped": True,
                "reason": f"No checker implemented for {provider}",
                "finetune_ids": finetune_ids,
            }
            log(f"    ⏭️  No checker for {provider}")
            continue

        try:
            result = checker(finetune_ids)
        except Exception as e:
            result = {"skipped": True, "reason": f"{type(e).__name__}"}
        result["entries"] = entry_map[provider]
        results[provider] = result

        if result.get("skipped"):
            log(f"    ⏭️  Skipped: {result['reason']}")
        elif result.get("missing"):
            missing = result["missing"]
            log(f"    ❌ {len(missing)}/{len(finetune_ids)} missing")  # type: ignore[arg-type]
            for m in missing:  # type: ignore[union-attr]
                log(f"       - {m}")
        else:
            log(f"    ✅ {len(finetune_ids)}/{len(finetune_ids)} found")

    return {"type": "static", "results": results}


# ---------------------------------------------------------------------------
# Fireworks dynamic model check
# ---------------------------------------------------------------------------


def _fireworks_supported_full_paths() -> set[str]:
    """Build full Fireworks model paths from the canonical allowlist in fireworks_finetune.py.

    The allowlist uses bare tail IDs (e.g. "qwen3-8b") but the Fireworks API
    returns full paths (e.g. "accounts/fireworks/models/qwen3-8b"). This function
    prepends the prefix so we can cross-reference.
    """
    return {
        f"{FIREWORKS_MODEL_PREFIX}{tail}"
        for tail in FIREWORKS_SUPPORTED_FINETUNE_MODELS
    }


def check_fireworks() -> dict:
    api_key = get_api_key("FIREWORKS_API_KEY")
    if not api_key:
        return {
            "type": "fireworks",
            "skipped": True,
            "reason": "FIREWORKS_API_KEY not set",
        }

    try:
        tunable = fetch_fireworks_tunable(api_key)
    except (RuntimeError, ValueError, OSError) as e:
        return {"type": "fireworks", "skipped": True, "reason": type(e).__name__}

    log(f"  Fireworks API reports {len(tunable)} supervised-tunable models")

    # Scrape the Fireworks docs page for the ground-truth supported models
    docs_models: set[str] | None = None
    try:
        docs_models = fetch_fireworks_docs_models()
        log(f"  Fireworks docs list {len(docs_models)} supported models")
    except (RuntimeError, OSError) as e:
        log(f"  ⚠️  Could not scrape Fireworks docs: {type(e).__name__}")
        log("     Falling back to allowlist-only comparison")

    allowlist = FIREWORKS_SUPPORTED_FINETUNE_MODELS

    # If docs scraping succeeded, check for allowlist drift against docs
    if docs_models is not None:
        in_docs_not_allowlist = sorted(docs_models - allowlist)
        in_allowlist_not_docs = sorted(allowlist - docs_models)

        if in_docs_not_allowlist:
            log(
                f"  ❌ {len(in_docs_not_allowlist)} models in docs but NOT in our allowlist (need to add):"
            )
            for m in in_docs_not_allowlist:
                log(f"     - {m}")
        if in_allowlist_not_docs:
            log(
                f"  ❌ {len(in_allowlist_not_docs)} models in our allowlist but NOT in docs (need to remove):"
            )
            for m in in_allowlist_not_docs:
                log(f"     - {m}")
        if not in_docs_not_allowlist and not in_allowlist_not_docs:
            log(f"  ✅ Allowlist matches docs exactly ({len(allowlist)} models)")
    else:
        in_docs_not_allowlist = []
        in_allowlist_not_docs = []

    # Also compare allowlist against API (secondary signal)
    supported = _fireworks_supported_full_paths()
    tunable_ids = {m["id"] for m in tunable}

    in_both = sorted(tunable_ids & supported)
    in_api_only = sorted(tunable_ids - supported)
    in_supported_only = sorted(supported - tunable_ids)

    log(f"  ✅ {len(in_both)} allowlist models found in API")
    if in_supported_only:
        log(
            f"  ❌ {len(in_supported_only)} allowlist models NOT in API (possibly stale):"
        )
        for m in in_supported_only:
            log(f"     - {m}")

    return {
        "type": "fireworks",
        "total_tunable": len(tunable),
        "allowlist_count": len(allowlist),
        "docs_count": len(docs_models) if docs_models else None,
        "docs_vs_allowlist": {
            "in_docs_not_allowlist": in_docs_not_allowlist,
            "in_allowlist_not_docs": in_allowlist_not_docs,
        },
        "api_vs_allowlist": {
            "in_both": in_both,
            "in_api_only_count": len(in_api_only),
            "in_allowlist_not_api": in_supported_only,
        },
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Check fine-tunable model availability"
    )
    parser.add_argument(
        "mode",
        choices=["static", "fireworks", "all"],
        help="Which check to run",
    )
    args = parser.parse_args()

    results = {}

    if args.mode in ("static", "all"):
        log("Checking static provider_finetune_id entries...")
        results["static"] = check_static()
        log()

    if args.mode in ("fireworks", "all"):
        log("Checking Fireworks dynamic tunable models...")
        results["fireworks"] = check_fireworks()
        log()

    json.dump(results, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
