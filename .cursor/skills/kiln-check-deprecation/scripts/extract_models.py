#!/usr/bin/env python3
"""Extract all non-deprecated KilnModelProvider entries from ml_model_list.py.

Outputs JSON to stdout with:
  - deprecated_count: number of already-deprecated entries
  - providers: dict of provider_name -> sorted unique list of model_ids
  - entries: list of {enum, provider, model_id, line} for mapping back to code

Also prints a human-readable summary to stderr.

Usage:
    python3 .cursor/skills/kiln-check-deprecation/scripts/extract_models.py > /tmp/kiln_extracted.json
"""

import json
import os
import re
import sys

REPO_ROOT = os.path.dirname(
    os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )
)
MODEL_LIST_PATH = os.path.join(REPO_ROOT, "libs/core/kiln_ai/adapters/ml_model_list.py")

SKIP_PROVIDERS = {
    "ollama",
    "docker_model_runner",
    "kiln_fine_tune",
    "kiln_custom_registry",
    "openai_compatible",
    "azure_openai",
    "huggingface",
}


def extract():
    with open(MODEL_LIST_PATH, "r") as f:
        lines = f.readlines()

    entries = []
    providers: dict[str, list[str]] = {}
    deprecated_count = 0
    current_model_enum = None

    i = 0
    while i < len(lines):
        line = lines[i]

        # Track the parent KilnModel's name=ModelName.xxx
        # This field uses `name=ModelName.xxx` (not `model_name=`).
        mn_match = re.search(r"name=ModelName\.(\w+)", line)
        if mn_match:
            current_model_enum = mn_match.group(1)

        if "KilnModelProvider(" in line and "class KilnModelProvider" not in line:
            block = line
            start_line = i + 1
            paren_count = line.count("(") - line.count(")")
            j = i + 1
            while paren_count > 0 and j < len(lines):
                block += lines[j]
                paren_count += lines[j].count("(") - lines[j].count(")")
                j += 1

            if "deprecated=True" in block:
                deprecated_count += 1
                i = j
                continue

            # Provider field uses `name=ModelProviderName.xxx` (not `provider_name=`).
            pn_match = re.search(r"name=ModelProviderName\.(\w+)", block)
            mid_match = re.search(r'model_id="([^"]+)"', block)

            if pn_match and mid_match and current_model_enum:
                provider_name = pn_match.group(1)
                model_id = mid_match.group(1)

                if provider_name not in providers:
                    providers[provider_name] = []
                providers[provider_name].append(model_id)

                entries.append(
                    {
                        "enum": current_model_enum,
                        "provider": provider_name,
                        "model_id": model_id,
                        "line": start_line,
                    }
                )

            i = j
        else:
            i += 1

    unique_providers: dict[str, list[str]] = {}
    for p, models in sorted(providers.items()):
        seen: set[str] = set()
        unique: list[str] = []
        for m in models:
            if m not in seen:
                seen.add(m)
                unique.append(m)
        unique_providers[p] = sorted(unique)

    return {
        "deprecated_count": deprecated_count,
        "providers": unique_providers,
        "entries": entries,
    }


def main():
    result = extract()

    print(f"Already deprecated: {result['deprecated_count']}", file=sys.stderr)
    print(file=sys.stderr)
    for p, models in sorted(result["providers"].items()):
        tag = " (SKIP)" if p in SKIP_PROVIDERS else ""
        print(f"  {p}: {len(models)} models{tag}", file=sys.stderr)
    print(file=sys.stderr)
    print(
        f"Total active entries: {len(result['entries'])} "
        f"across {len(result['providers'])} providers",
        file=sys.stderr,
    )

    json.dump(result, sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
