#!/usr/bin/env python3
"""Check model availability for one or all providers against extracted Kiln data.

Fetches each provider's model list via its API and cross-references against
the extracted JSON from extract_models.py. Reports missing models and
(for OpenRouter) upcoming expirations.

Usage:
    # Check a single provider
    python3 .cursor/skills/kiln-check-deprecation/scripts/check_provider.py openrouter

    # Check all configured providers
    python3 .cursor/skills/kiln-check-deprecation/scripts/check_provider.py all

    # Use a custom extracted JSON path
    python3 .cursor/skills/kiln-check-deprecation/scripts/check_provider.py all --extracted /tmp/my_extract.json

Requires:
    - Extracted JSON from extract_models.py at /tmp/kiln_extracted.json (or --extracted path)
    - API keys set as environment variables (source .env first)
    - required_permissions: ["all"] when run via Cursor Shell (network access needed)

API format quirks handled by this script:
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
import re
import subprocess
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

PROVIDER_CONFIG = {
    "openrouter": {
        "type": "openrouter",
        "url": "https://openrouter.ai/api/v1/models",
    },
    "openai": {
        "type": "openai_compat",
        "url": "https://api.openai.com/v1/models",
        "env": "OPENAI_API_KEY",
    },
    "anthropic": {
        "type": "anthropic",
        "url": "https://api.anthropic.com/v1/models",
        "env": "ANTHROPIC_API_KEY",
    },
    "gemini_api": {
        "type": "gemini",
        "env": "GEMINI_API_KEY",
    },
    "fireworks_ai": {
        "type": "fireworks",
        "env": "FIREWORKS_API_KEY",
    },
    "together_ai": {
        "type": "openai_compat",
        "url": "https://api.together.xyz/v1/models",
        "env": "TOGETHER_API_KEY",
    },
    "siliconflow_cn": {
        "type": "openai_compat",
        "url": "https://api.siliconflow.cn/v1/models",
        "env": "SILICONFLOW_CN_API_KEY",
    },
    "cerebras": {
        "type": "openai_compat",
        "url": "https://api.cerebras.ai/v1/models",
        "env": "CEREBRAS_API_KEY",
    },
    "groq": {
        "type": "openai_compat",
        "url": "https://api.groq.com/openai/v1/models",
        "env": "GROQ_API_KEY",
    },
    "vertex": {
        "type": "vertex",
        "env": "VERTEX_PROJECT_ID",
    },
}

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

CASE_INSENSITIVE_PROVIDERS = {"siliconflow_cn"}


def fetch_json(url: str, headers: dict | None = None, timeout: int = 30) -> Any:
    req = Request(url)
    req.add_header("User-Agent", "kiln-deprecation-check/1.0")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


# OpenRouter virtual suffixes that are never listed in the API.
# If a Kiln model_id has one of these, strip it and check the base model instead.
OPENROUTER_VIRTUAL_SUFFIXES = (":exacto",)


def fetch_openrouter() -> tuple[set[str], dict[str, str]]:
    data = fetch_json("https://openrouter.ai/api/v1/models")
    ids: set[str] = set()
    expiring: dict[str, str] = {}
    for m in data["data"]:
        ids.add(m["id"])
        if m.get("expiration_date"):
            expiring[m["id"]] = m["expiration_date"]
    return ids, expiring


def fetch_openai_compat(url: str, api_key: str) -> set[str]:
    """Handles both {data:[...]} (most providers) and flat [...] (Together AI)."""
    headers = {"Authorization": f"Bearer {api_key}"}
    data = fetch_json(url, headers)
    if isinstance(data, list):
        return {m["id"] for m in data}
    return {m["id"] for m in data["data"]}


def fetch_anthropic(api_key: str) -> set[str]:
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }
    data = fetch_json("https://api.anthropic.com/v1/models", headers)
    return {m["id"] for m in data["data"]}


def fetch_gemini(api_key: str) -> set[str]:
    """Fetches from both v1 and v1beta — preview/Gemma models only appear on v1beta."""
    ids: set[str] = set()
    errors: list[str] = []
    for version in ("v1", "v1beta"):
        url = f"https://generativelanguage.googleapis.com/{version}/models?key={api_key}&pageSize=100"
        try:
            data = fetch_json(url)
            for m in data.get("models", []):
                ids.add(m["name"].removeprefix("models/"))
        except (HTTPError, URLError, OSError, KeyError, ValueError) as e:
            errors.append(f"{version}: {e}")
    if not ids and errors:
        raise RuntimeError(f"All Gemini endpoints failed: {'; '.join(errors)}")
    return ids


def fetch_vertex(project_id: str) -> set[str]:
    """Fetch models from Vertex AI publisher listing across google/anthropic/meta.

    Requires gcloud CLI auth. Uses v1beta1 endpoint with x-goog-user-project header.
    Model names come as 'publishers/{pub}/models/{name}' — we extract just {name}.
    Kiln Vertex entries may use a 'meta/' prefix for LiteLLM routing — callers should
    strip this before comparing.
    """
    token = subprocess.check_output(
        ["gcloud", "auth", "print-access-token"], text=True
    ).strip()

    ids: set[str] = set()
    errors: list[str] = []
    for publisher in ("google", "anthropic", "meta"):
        url = f"https://us-central1-aiplatform.googleapis.com/v1beta1/publishers/{publisher}/models"
        req = Request(url)
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("x-goog-user-project", project_id)
        req.add_header("User-Agent", "kiln-deprecation-check/1.0")
        try:
            with urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
                for m in data.get("publisherModels", []):
                    ids.add(m["name"].split("/")[-1])
        except (HTTPError, URLError, OSError, KeyError, ValueError) as e:
            errors.append(f"{publisher}: {e}")
    if not ids and errors:
        raise RuntimeError(f"All Vertex publishers failed: {'; '.join(errors)}")
    return ids


def fetch_fireworks_individual(api_key: str, model_ids: list[str]) -> set[str]:
    """Check each model via Fireworks model detail API.

    The /v1/models listing only returns serverless models, but models may still
    be available via on-demand deployments. The detail API at
    GET https://api.fireworks.ai/v1/{model_id} returns info for ALL models
    regardless of deployment tier. Returns 404 only for truly removed models.
    """
    available: set[str] = set()
    for model_id in model_ids:
        url = f"https://api.fireworks.ai/v1/{model_id}"
        req = Request(url)
        req.add_header("Authorization", f"Bearer {api_key}")
        req.add_header("User-Agent", "kiln-deprecation-check/1.0")
        try:
            with urlopen(req, timeout=10) as _:
                available.add(model_id)
        except HTTPError as e:
            if e.code == 404:
                continue
            raise
    return available


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
        available = fetch_vertex(api_key)
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

    if provider_name == "vertex":
        available_with_aliases = set(available)
        for a in available:
            if re.match(r".*-\d{3}$", a):
                available_with_aliases.add(re.sub(r"-\d{3}$", "", a))
        available = available_with_aliases

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


def _log(msg: str = "") -> None:
    sys.stderr.write(msg + "\n")


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
        _log(f"Checking {provider}...")
        try:
            result = check_provider(provider, extracted)
            results[provider] = result

            if result.get("skipped"):
                _log(f"  ⏭️  Skipped: {result['reason']}")
            elif result.get("error"):
                _log(f"  ❗ Error: {result['error']}")
            elif result["missing_count"] > 0:
                _log(
                    f"  ❌ {result['missing_count']}/{result['kiln_count']} missing "
                    f"(provider has {result['available_count']} models total)"
                )
                for m in result["missing"]:
                    _log(f"     - {m}")
                if result.get("expiring"):
                    for e in result["expiring"]:
                        _log(f"  ⚠️  Expiring: {e['model_id']} ({e['expiration_date']})")
            else:
                msg = f"  ✅ {result['kiln_count']}/{result['kiln_count']} found"
                if result.get("expiring"):
                    msg += f" ({len(result['expiring'])} expiring soon)"
                _log(msg)
                for e in result.get("expiring", []):
                    _log(f"  ⚠️  Expiring: {e['model_id']} ({e['expiration_date']})")
        except (HTTPError, URLError, OSError) as e:
            results[provider] = {"provider": provider, "error": str(e)}
            _log(f"  ❗ Network error: {e}")
        except Exception as e:
            results[provider] = {"provider": provider, "error": str(e)}
            _log(f"  ❗ Error: {e}")

    json.dump(results, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
