"""Shared provider API utilities for Kiln model-checking skills.

Provides functions to fetch model listings from each provider's API,
plus common helpers. Used by both the deprecation check and
fine-tune deprecation check skills.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


def find_repo_root() -> Path:
    """Walk up from this file to find the repo root (directory containing .agents/)."""
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / ".agents").is_dir() and (current / "libs").is_dir():
            return current
        current = current.parent
    raise RuntimeError("Could not find repo root")


# ---------------------------------------------------------------------------
# Provider configuration
# ---------------------------------------------------------------------------

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
    "featherless_ai": {
        # Featherless's model list is public — no key needed to enumerate models.
        "type": "openai_compat",
        "url": "https://api.featherless.ai/v1/models",
        "env": "FEATHERLESS_AI_API_KEY",
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
    "cloudflare": {
        # Credentials are optional: without them the public catalog JSON is used.
        "type": "cloudflare",
        "env": "CLOUDFLARE_API_KEY",
        "account_env": "CLOUDFLARE_ACCOUNT_ID",
    },
}

# Providers whose model listing works without credentials, so a missing key
# must not skip the check.
KEY_OPTIONAL_PROVIDERS = {"cloudflare"}

CLOUDFLARE_API_BASE = "https://api.cloudflare.com/client/v4"
CLOUDFLARE_PUBLIC_MODELS_URL = "https://ai-cloudflare-com.pages.dev/api/models"
CLOUDFLARE_TEXT_GENERATION_TASK = "Text Generation"
CLOUDFLARE_SEARCH_PAGE_SIZE = 100

SKIP_PROVIDERS = {
    "amazon_bedrock",
    "ollama",
    "docker_model_runner",
    "kiln_fine_tune",
    "kiln_custom_registry",
    "openai_compatible",
    "azure_openai",
    "huggingface",
    # TypeSafe AI's System One API has no OpenAI-compatible model listing to enumerate.
    "typesafe",
}

CASE_INSENSITIVE_PROVIDERS = {"siliconflow_cn"}

# OpenRouter virtual suffixes that are never listed in the API.
OPENROUTER_VIRTUAL_SUFFIXES = (":exacto",)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def log(msg: str = "") -> None:
    sys.stderr.write(msg + "\n")


def fetch_json(url: str, headers: dict | None = None, timeout: int = 30) -> Any:
    req = Request(url)
    req.add_header("User-Agent", "kiln-model-check/1.0")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def get_api_key(env_var: str) -> str | None:
    """Return the API key from environment, or None if not set."""
    val = os.environ.get(env_var, "")
    return val if val else None


# ---------------------------------------------------------------------------
# Provider model-listing functions
#
# Each returns a set of model IDs available on the provider.
# ---------------------------------------------------------------------------


def fetch_openrouter() -> tuple[set[str], dict[str, str]]:
    """Returns (model_ids, expiring_dict) from OpenRouter. No auth required."""
    data = fetch_json("https://openrouter.ai/api/v1/models")
    ids: set[str] = set()
    expiring: dict[str, str] = {}
    for m in data["data"]:
        ids.add(m["id"])
        if m.get("expiration_date"):
            expiring[m["id"]] = m["expiration_date"]
    return ids, expiring


def fetch_openai_compat(url: str, api_key: str) -> set[str]:
    """Fetch model IDs from an OpenAI-compatible /v1/models endpoint.

    Handles both {data:[...]} (most providers) and flat [...] (Together AI).
    """
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
        url = f"https://generativelanguage.googleapis.com/{version}/models?pageSize=100"
        try:
            data = fetch_json(url, {"x-goog-api-key": api_key})
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
    try:
        token = subprocess.check_output(
            ["gcloud", "auth", "print-access-token"], text=True
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        raise RuntimeError(f"gcloud auth failed: {e}") from e

    ids: set[str] = set()
    errors: list[str] = []
    for publisher in ("google", "anthropic", "meta"):
        next_page_token: str | None = None
        while True:
            url = (
                "https://us-central1-aiplatform.googleapis.com/"
                f"v1beta1/publishers/{publisher}/models?listAllVersions=true"
            )
            if next_page_token:
                url += f"&pageToken={next_page_token}"

            req = Request(url)
            req.add_header("Authorization", f"Bearer {token}")
            req.add_header("x-goog-user-project", project_id)
            req.add_header("User-Agent", "kiln-model-check/1.0")
            try:
                with urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read())
                    for m in data.get("publisherModels", []):
                        ids.add(m["name"].split("/")[-1])
                    next_page_token = data.get("nextPageToken")
                    if not next_page_token:
                        break
            except (HTTPError, URLError, OSError, KeyError, ValueError) as e:
                errors.append(f"{publisher}: {e}")
                break
    if not ids and errors:
        raise RuntimeError(f"All Vertex publishers failed: {'; '.join(errors)}")
    return ids


def fetch_vertex_with_aliases(project_id: str) -> set[str]:
    """Like fetch_vertex but also adds unversioned aliases (e.g. gemini-2.0-flash-001 -> gemini-2.0-flash)."""
    ids = fetch_vertex(project_id)
    with_aliases = set(ids)
    for model_id in ids:
        if re.match(r".*-\d{3}$", model_id):
            with_aliases.add(re.sub(r"-\d{3}$", "", model_id))
    return with_aliases


def _cloudflare_property(model: dict, property_id: str) -> Any:
    for prop in model.get("properties") or []:
        if prop.get("property_id") == property_id:
            return prop.get("value")
    return None


def _fetch_cloudflare_search(api_key: str, account_id: str) -> list[dict]:
    """Page through the official models-search API for text-generation models.

    include_deprecated=true keeps models visible for up to three months after
    retirement, so their planned_deprecation_date is still reported.
    """
    headers = {"Authorization": f"Bearer {api_key}"}
    models: list[dict] = []
    seen: set[str] = set()
    page = 1
    while True:
        url = (
            f"{CLOUDFLARE_API_BASE}/accounts/{quote(account_id, safe='')}/ai/models/search"
            f"?task=Text%20Generation&include_deprecated=true"
            f"&per_page={CLOUDFLARE_SEARCH_PAGE_SIZE}&page={page}"
        )
        data = fetch_json(url, headers)
        if not data.get("success", False):
            raise RuntimeError(f"Cloudflare models search failed: {data.get('errors')}")
        batch = data.get("result") or []
        new = [m for m in batch if m.get("name") not in seen]
        models.extend(new)
        seen.update(m.get("name") for m in new)
        if not new or len(batch) < CLOUDFLARE_SEARCH_PAGE_SIZE:
            return models
        page += 1


def _fetch_cloudflare_public(attempts: int = 3) -> list[dict]:
    """Fetch Cloudflare's public, unauthenticated model catalog (~900 KB).

    The endpoint sometimes returns a transient 502, so retry a few times.
    """
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return fetch_json(CLOUDFLARE_PUBLIC_MODELS_URL, timeout=60)["models"]
        except OSError as e:
            last_error = e
            if attempt + 1 < attempts:
                time.sleep(2)
    raise RuntimeError(f"Cloudflare public model catalog failed: {last_error}")


def cloudflare_availability(
    models: list[dict], today: date
) -> tuple[set[str], dict[str, str]]:
    """Split Cloudflare model records into (available_ids, deprecation_dates).

    Only text-generation models count. A model whose planned_deprecation_date
    is today or earlier is retired: it is left out of available_ids even if
    the listing still shows it, because Cloudflare may silently alias a
    retired ID to a different model. Every dated model is returned in
    deprecation_dates so it can be removed before the date.
    """
    available: set[str] = set()
    deprecation_dates: dict[str, str] = {}
    for model in models:
        task = model.get("task") or {}
        if task.get("name") != CLOUDFLARE_TEXT_GENERATION_TASK:
            continue
        name = model["name"]
        planned = _cloudflare_property(model, "planned_deprecation_date")
        if planned:
            deprecation_dates[name] = str(planned)
            try:
                if date.fromisoformat(str(planned)) <= today:
                    continue
            except ValueError:
                pass
        available.add(name)
    return available, deprecation_dates


def fetch_cloudflare(
    api_key: str | None, account_id: str | None
) -> tuple[set[str], dict[str, str]]:
    """Returns (model_ids, deprecation_dates) for Cloudflare Workers AI.

    Uses the authenticated models-search API when both credentials are set,
    otherwise the public catalog JSON. Never use LiteLLM's Cloudflare catalog:
    it is months stale.
    """
    if api_key and account_id:
        models = _fetch_cloudflare_search(api_key, account_id)
    else:
        models = _fetch_cloudflare_public()
    return cloudflare_availability(models, date.today())


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
        req.add_header("User-Agent", "kiln-model-check/1.0")
        try:
            with urlopen(req, timeout=10) as _:
                available.add(model_id)
        except HTTPError as e:
            if e.code == 404:
                continue
            raise
    return available


def fetch_fireworks_tunable(api_key: str) -> list[dict]:
    """Fetch all models that support supervised fine-tuning from Fireworks API.

    Uses the supervisedLoraTunable and supervisedFullParameterTunable fields,
    which are accurate. The older tunable field is stale and unreliable.

    Returns list of dicts with keys: id, display_name, supports_tools.
    """
    url = "https://api.fireworks.ai/v1/accounts/fireworks/models"
    headers = {"Authorization": f"Bearer {api_key}"}

    models: list[dict] = []
    page_url = f"{url}?pageSize=200"

    while True:
        data = fetch_json(page_url, headers)
        if "models" not in data or not isinstance(data["models"], list):
            raise ValueError("Invalid Fireworks response: expected 'models' key")
        models.extend(data["models"])
        next_token = data.get("nextPageToken")
        if next_token and isinstance(next_token, str) and len(next_token) > 0:
            page_url = f"{url}?pageSize=200&pageToken={next_token}"
        else:
            break

    tunable = []
    for m in models:
        is_supervised_tunable = m.get("supervisedLoraTunable", False) or m.get(
            "supervisedFullParameterTunable", False
        )
        if is_supervised_tunable:
            tunable.append(
                {
                    "id": m.get("name", ""),
                    "display_name": m.get("displayName", ""),
                    "supports_tools": m.get("supportsTools", False),
                }
            )

    return tunable


def fetch_fireworks_docs_models() -> set[str]:
    """Scrape Fireworks docs page to get the list of officially supported fine-tune models.

    Parses the "Supported base models" table from the managed fine-tuning docs.
    Returns bare tail IDs (e.g. "qwen3-8b") matching the format used in
    FIREWORKS_SUPPORTED_FINETUNE_MODELS.

    Raises RuntimeError if the page can't be fetched or the table can't be parsed.
    """
    url = "https://docs.fireworks.ai/fine-tuning/managed-finetuning-intro"
    req = Request(url)
    req.add_header("User-Agent", "kiln-model-check/1.0")
    with urlopen(req, timeout=15) as resp:
        html = resp.read().decode("utf-8")

    # Find the supported base models table by locating a known model ID
    # then walking back to the table start
    marker = html.find("<td><code>")
    if marker < 0:
        raise RuntimeError("Could not find model table in Fireworks docs page")

    table_start = html.rfind("<table", 0, marker)
    table_end = html.find("</table>", marker)
    if table_start < 0 or table_end < 0:
        raise RuntimeError("Could not find table boundaries in Fireworks docs page")

    table_html = html[table_start:table_end]
    model_ids = set(re.findall(r"<td><code>([^<]+)</code></td>", table_html))

    if not model_ids:
        raise RuntimeError("Parsed zero models from Fireworks docs table")

    return model_ids


def fetch_together_docs_models() -> set[str]:
    """Scrape Together AI docs page to get the list of supported fine-tune models.

    Parses the fine-tuning models page for model IDs in org/model format
    (e.g. "meta-llama/Meta-Llama-3.1-8B-Instruct-Reference").

    Raises RuntimeError if the page can't be fetched or no models are found.
    """
    url = "https://docs.together.ai/docs/fine-tuning-models"
    req = Request(url)
    req.add_header("User-Agent", "kiln-model-check/1.0")
    with urlopen(req, timeout=15) as resp:
        html = resp.read().decode("utf-8")

    # Model IDs appear as >org/model-name< in table cells
    model_ids = set(re.findall(r">([A-Za-z][\w\-]+/[\w\.\-]+)<", html))

    if not model_ids:
        raise RuntimeError("Parsed zero models from Together docs page")

    return model_ids
