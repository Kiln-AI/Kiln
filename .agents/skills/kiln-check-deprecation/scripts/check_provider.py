#!/usr/bin/env python3
"""Check model availability for one or all providers against extracted Kiln data.

Fetches each provider's model list via its API and cross-references against
the extracted JSON from extract_models.py. Reports missing models and
(for OpenRouter) upcoming expirations.

Usage:
    # Check a single provider
    python3 .agents/skills/kiln-check-deprecation/scripts/check_provider.py openrouter

    # Check all configured providers
    python3 .agents/skills/kiln-check-deprecation/scripts/check_provider.py all

    # Use a custom extracted JSON path
    python3 .agents/skills/kiln-check-deprecation/scripts/check_provider.py all --extracted /tmp/my_extract.json

Requires:
    - Extracted JSON from extract_models.py at /tmp/kiln_extracted.json (or --extracted path)
    - API keys set as environment variables (source .env first)
    - required_permissions: ["all"] when run via Cursor Shell (network access needed)

API format quirks handled by the shared provider_api module:
    - Together AI returns a flat JSON array, not {data: [...]}
    - Gemini API needs both v1 and v1beta endpoints (preview models only on v1beta)
    - Gemini model names are prefixed with "models/" — stripped automatically
    - Anthropic uses x-api-key header, not Authorization Bearer
    - OpenRouter is public (no auth) and includes expiration_date fields
    - OpenRouter :exacto is a virtual routing suffix — never listed in the API.
      The script strips :exacto before comparing. :free and :thinking ARE real
      model entries that appear in the listing when available.
    - SiliconFlow API is case-insensitive (e.g. "glm-4.6v" == "GLM-4.6V") but
      the listing returns canonical casing. The script does case-insensitive matching.
    - Fireworks /v1/models only lists serverless models; this script uses the model
      detail API (GET /v1/{model_id}) to check each model individually, since models
      may still be available via on-demand deployments even when off the serverless tier
"""

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError

# Add shared scripts directory to path
# Script is at .agents/skills/<skill>/scripts/<file>.py
# parent chain: scripts -> <skill> -> skills -> .agents
sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent.parent.parent / "scripts")
)

from provider_utils import (  # type: ignore[import-not-found]
    CASE_INSENSITIVE_PROVIDERS,
    OPENROUTER_VIRTUAL_SUFFIXES,
    PROVIDER_CONFIG,
    SKIP_PROVIDERS,
    fetch_anthropic,
    fetch_fireworks_individual,
    fetch_gemini,
    fetch_openai_compat,
    fetch_openrouter,
    fetch_vertex_with_aliases,
    log,
)


def check_provider(provider_name: str, extracted: dict) -> dict:
    config = PROVIDER_CONFIG.get(provider_name)
    if not config:
        return {"provider": provider_name, "error": "Unknown/unsupported provider"}

    kiln_models = extracted["providers"].get(provider_name, [])
    if not kiln_models:
        return {"provider": provider_name, "error": "No Kiln models for this provider"}

    env_var = config.get("env")
    api_key = ""
    if env_var:
        api_key = os.environ.get(env_var, "")
        if not api_key:
            return {
                "provider": provider_name,
                "skipped": True,
                "reason": f"{env_var} not set",
            }

    expiring: dict[str, str] = {}
    ptype = config["type"]

    if ptype == "openrouter":
        available, expiring = fetch_openrouter()
    elif ptype == "anthropic":
        available = fetch_anthropic(api_key)
    elif ptype == "gemini":
        available = fetch_gemini(api_key)
    elif ptype == "fireworks":
        available = fetch_fireworks_individual(api_key, kiln_models)
    elif ptype == "vertex":
        available = fetch_vertex_with_aliases(api_key)
    elif ptype == "openai_compat":
        available = fetch_openai_compat(config["url"], api_key)
    else:
        return {"provider": provider_name, "error": f"Unknown type: {ptype}"}

    case_insensitive = provider_name in CASE_INSENSITIVE_PROVIDERS
    if case_insensitive:
        available = {m.lower() for m in available}

    def _effective_id(model_id: str) -> str:
        mid = model_id
        if provider_name == "openrouter":
            for suffix in OPENROUTER_VIRTUAL_SUFFIXES:
                if mid.endswith(suffix):
                    mid = mid.removesuffix(suffix)
        if provider_name == "vertex":
            mid = mid.split("/")[-1]
        if case_insensitive:
            mid = mid.lower()
        return mid

    missing = sorted(m for m in kiln_models if _effective_id(m) not in available)
    expiring_entries = sorted(
        [
            {"model_id": m, "expiration_date": expiring[_effective_id(m)]}
            for m in kiln_models
            if _effective_id(m) in expiring
        ],
        key=lambda e: e["expiration_date"],
    )
    missing_set = set(missing)
    entries_to_deprecate = [
        e
        for e in extracted["entries"]
        if e["provider"] == provider_name and e["model_id"] in missing_set
    ]

    return {
        "provider": provider_name,
        "available_count": len(available),
        "kiln_count": len(kiln_models),
        "missing": missing,
        "missing_count": len(missing),
        "expiring": expiring_entries,
        "entries_to_deprecate": entries_to_deprecate,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Check provider model availability against Kiln model list"
    )
    parser.add_argument(
        "provider",
        help="Provider name to check, or 'all' to check every configured provider",
    )
    parser.add_argument(
        "--extracted",
        default="/tmp/kiln_extracted.json",
        help="Path to extracted JSON from extract_models.py (default: /tmp/kiln_extracted.json)",
    )
    args = parser.parse_args()

    with open(args.extracted) as f:
        extracted = json.load(f)

    if args.provider == "all":
        providers = sorted(p for p in extracted["providers"] if p not in SKIP_PROVIDERS)
    else:
        providers = [args.provider]

    results = {}
    for provider in providers:
        log(f"Checking {provider}...")
        try:
            result = check_provider(provider, extracted)
            results[provider] = result

            if result.get("skipped"):
                log(f"  ⏭️  Skipped: {result['reason']}")
            elif result.get("error"):
                log(f"  ❗ Error: {result['error']}")
            elif result["missing_count"] > 0:
                log(
                    f"  ❌ {result['missing_count']}/{result['kiln_count']} missing "
                    f"(provider has {result['available_count']} models total)"
                )
                for m in result["missing"]:
                    log(f"     - {m}")
                if result.get("expiring"):
                    for e in result["expiring"]:
                        log(f"  ⚠️  Expiring: {e['model_id']} ({e['expiration_date']})")
            else:
                msg = f"  ✅ {result['kiln_count']}/{result['kiln_count']} found"
                if result.get("expiring"):
                    msg += f" ({len(result['expiring'])} expiring soon)"
                log(msg)
                for e in result.get("expiring", []):
                    log(f"  ⚠️  Expiring: {e['model_id']} ({e['expiration_date']})")
        except (HTTPError, URLError, OSError) as e:
            results[provider] = {"provider": provider, "error": str(e)}
            log(f"  ❗ Network error: {e}")
        except Exception as e:
            results[provider] = {"provider": provider, "error": str(e)}
            log(f"  ❗ Error: {e}")

    json.dump(results, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
