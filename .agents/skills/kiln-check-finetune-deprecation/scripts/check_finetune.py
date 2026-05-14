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
import re
import sys
from pathlib import Path

# Add shared scripts directory to path
# Script is at .agents/skills/<skill>/scripts/<file>.py
# parent chain: scripts -> <skill> -> skills -> .agents
sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent.parent.parent / "scripts")
)

from provider_utils import (  # type: ignore[import-not-found]
    fetch_fireworks_tunable,
    fetch_openai_compat,
    fetch_vertex_with_aliases,
    find_repo_root,
    get_api_key,
    log,
)

MODEL_LIST_PATH = (
    find_repo_root() / "libs" / "core" / "kiln_ai" / "adapters" / "ml_model_list.py"
)


# ---------------------------------------------------------------------------
# Extract static provider_finetune_id entries from ml_model_list.py
# ---------------------------------------------------------------------------


def extract_static_finetune_ids() -> list[dict]:
    """Parse ml_model_list.py to find all provider_finetune_id entries.

    Returns list of {model_name, provider, finetune_id} dicts.
    """
    source = MODEL_LIST_PATH.read_text()
    entries: list[dict] = []

    model_pattern = re.compile(
        r"KilnModel\s*\((.*?)\n    \)",
        re.DOTALL,
    )
    name_pattern = re.compile(r'friendly_name\s*=\s*"([^"]+)"')
    provider_block_pattern = re.compile(
        r"KilnModelProvider\s*\((.*?)\)",
        re.DOTALL,
    )
    provider_name_pattern = re.compile(r"name\s*=\s*ModelProviderName\.(\w+)")
    finetune_id_pattern = re.compile(r'provider_finetune_id\s*=\s*"([^"]+)"')

    for model_match in model_pattern.finditer(source):
        model_block = model_match.group(1)
        name_match = name_pattern.search(model_block)
        model_name = name_match.group(1) if name_match else "Unknown"

        for provider_match in provider_block_pattern.finditer(model_block):
            provider_block = provider_match.group(1)
            finetune_match = finetune_id_pattern.search(provider_block)
            if not finetune_match:
                continue

            pname_match = provider_name_pattern.search(provider_block)
            provider = pname_match.group(1) if pname_match else "unknown"

            entries.append(
                {
                    "model_name": model_name,
                    "provider": provider,
                    "finetune_id": finetune_match.group(1),
                }
            )

    return entries


# ---------------------------------------------------------------------------
# Check static providers
# ---------------------------------------------------------------------------


def check_openai_finetune(finetune_ids: list[str]) -> dict:
    api_key = get_api_key("OPENAI_API_KEY")
    if not api_key:
        return {"skipped": True, "reason": "OPENAI_API_KEY not set"}

    available = fetch_openai_compat("https://api.openai.com/v1/models", api_key)
    found = [fid for fid in finetune_ids if fid in available]
    missing = [fid for fid in finetune_ids if fid not in available]
    return {"found": found, "missing": missing, "available_count": len(available)}


def check_together_finetune(finetune_ids: list[str]) -> dict:
    api_key = get_api_key("TOGETHER_API_KEY")
    if not api_key:
        return {"skipped": True, "reason": "TOGETHER_API_KEY not set"}

    available = fetch_openai_compat("https://api.together.xyz/v1/models", api_key)
    found = [fid for fid in finetune_ids if fid in available]
    missing = [fid for fid in finetune_ids if fid not in available]
    return {"found": found, "missing": missing, "available_count": len(available)}


def check_vertex_finetune(finetune_ids: list[str]) -> dict:
    project_id = get_api_key("VERTEX_PROJECT_ID")
    if not project_id:
        return {"skipped": True, "reason": "VERTEX_PROJECT_ID not set"}

    try:
        available = fetch_vertex_with_aliases(project_id)
    except (RuntimeError, FileNotFoundError, Exception) as e:
        return {"skipped": True, "reason": f"Vertex API error: {e}"}

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
        "openai": check_openai_finetune,
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

        result = checker(finetune_ids)
        result["entries"] = entry_map[provider]
        results[provider] = result

        if result.get("skipped"):
            log(f"    ⏭️  Skipped: {result['reason']}")
        elif result.get("missing"):
            log(f"    ❌ {len(result['missing'])}/{len(finetune_ids)} missing")
            for m in result["missing"]:
                log(f"       - {m}")
        else:
            log(f"    ✅ {len(finetune_ids)}/{len(finetune_ids)} found")

    return {"type": "static", "results": results}


# ---------------------------------------------------------------------------
# Fireworks dynamic model check
# ---------------------------------------------------------------------------

# Known supported base models from Fireworks docs.
# Hardcoded because Fireworks' API `tunable` flag is unreliable — it marks ~167
# models as tunable when only ~15 are actually supported for fine-tuning. The docs
# page is the real source of truth, but it's HTML (not a structured API), so we
# maintain this list manually. Update it when Fireworks changes their supported models.
#
# Last updated: 2026-05-13
# Source: https://docs.fireworks.ai/fine-tuning/managed-finetuning-intro#supported-base-models
FIREWORKS_DOCUMENTED_MODELS = {
    "accounts/fireworks/models/llama-v3p1-8b-instruct",
    "accounts/fireworks/models/llama-v3p1-70b-instruct",
    "accounts/fireworks/models/llama-v3p1-405b-instruct",
    "accounts/fireworks/models/llama-v3p2-1b-instruct",
    "accounts/fireworks/models/llama-v3p2-3b-instruct",
    "accounts/fireworks/models/llama-v3p3-70b-instruct",
    "accounts/fireworks/models/llama4-scout-instruct-basic",
    "accounts/fireworks/models/llama4-maverick-instruct-basic",
    "accounts/fireworks/models/qwen2p5-72b-instruct",
    "accounts/fireworks/models/qwen2p5-coder-32b-instruct",
    "accounts/fireworks/models/qwen3-8b",
    "accounts/fireworks/models/qwen3-32b",
    "accounts/fireworks/models/deepseek-v3-0324",
    "accounts/fireworks/models/gemma-2-9b-it",
    "accounts/fireworks/models/phi-3-vision-128k-instruct",
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
    except Exception as e:
        return {"type": "fireworks", "skipped": True, "reason": str(e)}

    log(f"  Fireworks API reports {len(tunable)} tunable models")

    tunable_ids = {m["id"] for m in tunable}

    in_docs = sorted(tunable_ids & FIREWORKS_DOCUMENTED_MODELS)
    in_api_only = sorted(tunable_ids - FIREWORKS_DOCUMENTED_MODELS)
    in_docs_only = sorted(FIREWORKS_DOCUMENTED_MODELS - tunable_ids)

    log(f"  ✅ {len(in_docs)} models in both API and docs")
    if in_api_only:
        log(f"  ⚠️  {len(in_api_only)} models in API but NOT in docs (possibly stale):")
        for m in in_api_only:
            log(f"     - {m}")
    if in_docs_only:
        log(f"  ⚠️  {len(in_docs_only)} models in docs but NOT in API:")
        for m in in_docs_only:
            log(f"     - {m}")

    api_only_details = [m for m in tunable if m["id"] in set(in_api_only)]

    return {
        "type": "fireworks",
        "total_tunable": len(tunable),
        "documented_count": len(FIREWORKS_DOCUMENTED_MODELS),
        "in_both": in_docs,
        "in_api_only": api_only_details,
        "in_docs_only": in_docs_only,
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
