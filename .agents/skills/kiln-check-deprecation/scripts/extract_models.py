#!/usr/bin/env python3
"""Extract all non-deprecated KilnModelProvider entries from the remote config.

Fetches the published model list from remote-config.getkiln.ai and outputs
JSON to stdout with:
  - deprecated_count: number of already-deprecated entries
  - providers: dict of provider_name -> sorted unique list of model_ids
  - entries: list of {enum, provider, model_id} for each non-deprecated entry

Also prints a human-readable summary to stderr.

Usage:
    python3 .agents/skills/kiln-check-deprecation/scripts/extract_models.py > /tmp/kiln_extracted.json
"""

import json
import sys
from urllib.request import Request, urlopen

REMOTE_CONFIG_URL = "https://remote-config.getkiln.ai/kiln_config_v2.json"

SKIP_PROVIDERS = {
    "amazon_bedrock",
    "ollama",
    "docker_model_runner",
    "kiln_fine_tune",
    "kiln_custom_registry",
    "openai_compatible",
    "azure_openai",
    "huggingface",
}


def _log(msg: str = "") -> None:
    sys.stderr.write(msg + "\n")


def fetch_remote_config() -> dict:
    req = Request(REMOTE_CONFIG_URL)
    req.add_header("User-Agent", "kiln-deprecation-check/1.0")
    with urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def extract() -> dict:
    config = fetch_remote_config()

    entries: list[dict] = []
    providers: dict[str, list[str]] = {}
    deprecated_count = 0

    for model in config.get("model_list", []):
        model_enum = model.get("name", "")
        for p in model.get("providers", []):
            provider_name = p.get("name", "")
            model_id = p.get("model_id")

            if not model_id or not provider_name:
                continue

            if p.get("deprecated", False):
                deprecated_count += 1
                continue

            if provider_name not in providers:
                providers[provider_name] = []
            providers[provider_name].append(model_id)

            entries.append(
                {
                    "enum": model_enum,
                    "provider": provider_name,
                    "model_id": model_id,
                }
            )

    unique_providers: dict[str, list[str]] = {}
    for pname, models in sorted(providers.items()):
        seen: set[str] = set()
        unique: list[str] = []
        for m in models:
            if m not in seen:
                seen.add(m)
                unique.append(m)
        unique_providers[pname] = sorted(unique)

    return {
        "deprecated_count": deprecated_count,
        "providers": unique_providers,
        "entries": entries,
    }


def main() -> None:
    result = extract()

    _log(f"Already deprecated: {result['deprecated_count']}")
    _log()
    for p, models in sorted(result["providers"].items()):
        tag = " (SKIP)" if p in SKIP_PROVIDERS else ""
        _log(f"  {p}: {len(models)} models{tag}")
    _log()
    _log(
        f"Total active entries: {len(result['entries'])} "
        f"across {len(result['providers'])} providers"
    )

    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
