---
name: kiln-prerelease-check
description: Run the Kiln pre-release smoke test suite, the standard CI checks (checks.sh), and audit the prerelease test set for stale model pins or coverage gaps. Use when the user wants to validate a release candidate, run prerelease tests, or asks for a "prerelease check / smoke / audit / housekeeping".
---

# Kiln Pre-release Check

End-to-end pre-release verification: run the curated `@pytest.mark.prerelease` smoke set, run the standard CI checks (lint / format / typecheck / unit tests), and audit the prerelease set itself for staleness (e.g., a test pinned to a removed model, or a new provider with no smoke coverage).

The output of this skill is a written report dropped in `.prerelease/<timestamp>/` (this directory is gitignored).

---

## What "prerelease" means here

A prerelease test is a paid test (it makes real API calls) that we **cannot** meaningfully replace with a mock — its whole point is to verify a live third-party API still behaves how we depend on it. Examples: `test_connect_vertex_live`, basic OpenAI / Claude / Gemini calls, embedding API across providers, reranker integration, Fireworks fine-tune deployment listing, etc.

The set is a **curated subset of `@pytest.mark.paid`**. Tests carry both markers — `@pytest.mark.paid` for the cost gate, `@pytest.mark.prerelease` for the curated selection.

Concretely:

- `--runpaid` runs the full paid suite (slow, expensive, intended for one-off use).
- `--runprerelease` runs **only** the prerelease subset (still paid, but a small, focused, releaseable list). It implies `--runpaid` for those tests.

Marker registration lives in `pyproject.toml` (`[tool.pytest.ini_options].markers`); the flag is wired up in the top-level `conftest.py` via `pytest_addoption` + `pytest_collection_modifyitems`.

### Whitelist for litellm-adapter tests

Several paid tests (embeddings, document extraction, thinking-level reasoning) fan out across **every** `(model, provider)` pair in `ml_model_list.py` / `ml_embedding_model_list.py`. Running those under `--runprerelease` would be slow and expensive. Instead, those tests have dedicated `*_prerelease_smoke` sibling functions that iterate only over a small curated whitelist living in:

```
libs/core/kiln_ai/adapters/pytest_prerelease_whitelist.py
```

Whitelisted lists:

- `PRERELEASE_CHAT_MODELS` — handful of chat models, one per major provider (OpenAI + GPT-5, Anthropic + Claude Sonnet/Haiku, Gemini, OpenRouter, Groq, Fireworks, Together).
- `PRERELEASE_EMBEDDING_MODELS` — one embedding model per embedding-supporting provider.
- `PRERELEASE_EXTRACTION_MODELS` — one multimodal model per major vendor (OpenAI, Anthropic, Gemini).
- `PRERELEASE_EXTRACTION_MIME_PROBES` — three mime probes (PDF, PNG, MP3) for the extraction smoke; the full paid test sweeps all 13 mime types per model.
- `PRERELEASE_THINKING_MODELS` — five (provider, model, thinking_level) triples covering reasoning content + a "none" negation case.

When you maintain the prerelease set, **widen these lists** rather than tagging more fan-out tests. Conversely, if you add a brand-new family or provider, add one representative entry to the relevant list — not the entire fan-out.

The fan-out tests (e.g. `test_extract_document_success` over every model × mime type, `test_paid_generate_embeddings_basic` over every embedding) are **only `@pytest.mark.paid`** — they still exist for full paid-suite runs and for the per-model integration in `claude-maintain-models`. They do NOT carry `@pytest.mark.prerelease`.

---

## Global rules

- **Network access is required.** Every phase here makes real API calls or hits remote model-list endpoints. If you are running this skill inside a sandboxed Bash session, request `required_permissions: ["all"]` for the test commands.
- **Env vars:** Source `.env` before running anything that needs API keys:
  ```bash
  export $(grep -v '^#' .env | xargs)
  ```
  Provider-specific env vars the prerelease set may touch: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `GROQ_API_KEY`, `OPENROUTER_API_KEY`, `FIREWORKS_API_KEY`, `TOGETHER_API_KEY`, `SILICONFLOW_CN_API_KEY`, `COHERE_API_KEY`, `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY`, plus `KILN_TEST_VERTEX_PROJECT_ID` (+ optional `KILN_TEST_VERTEX_LOCATION`) for the Vertex live check, which also requires `gcloud auth application-default login` against a project with `aiplatform.googleapis.com` enabled.
- **Each missing key just skips the relevant test** (`pytest.skip(...)`). That isn't a prerelease failure — it's a coverage gap. Surface it in the report so the user can decide whether to provide the key and re-run.
- **`ml_model_list.py` never deletes entries — it only marks them `deprecated=True`.** So a slug missing from our list isn't a real signal you'll encounter. The signals that matter are:
  1. The provider entry has `deprecated=True` in our list.
  2. The provider itself rejects the slug at runtime (4xx / "model not found") — note our list trails provider deprecations, so this can happen *before* we've marked it deprecated.
  3. A newer non-deprecated sibling in the same family now exists in our list, regardless of whether the current pin is still working.
- **DO NOT touch real prod-path code to make a prerelease test pass.** This includes hardcoded model **probes** in prod (e.g. the connectivity check inside `connect_vertex` — see Phase 4d). The skill is allowed to *flag* a probe whose pinned model has a newer sibling, but bumping the prod slug is the user's call, not yours — write it up in the report findings and wait. A test failure tells you something. Two flavors:
  1. **Real regression** (the prod code is now wrong, or the provider broke in a way we should adapt to): **leave it broken**, write it up clearly in the report, do not silently patch the production source.
  2. **Stale test housekeeping** (the test hardcodes a model slug we lazily picked, and one of the three signals above applies). **You can update the test.** Pick a current non-deprecated model from the same family and update the parametrization or assertion. Keep these test-only changes scoped and clearly noted in the report.
  If you cannot confidently tell flavor 1 from flavor 2, treat it as flavor 1 and report it.
- **The newer-sibling sweep is mandatory, not "only when something fails."** Even on a fully green run, every hardcoded slug in `pytest_prerelease_whitelist.py` and in prerelease test parametrize lists must be cross-checked against `ml_model_list.py`. If a newer non-deprecated member of the same family exists, swap and re-run. Examples: `test_connect_vertex_live` pinned to Gemini 2.x while Gemini 3 is in our list → upgrade. `PRERELEASE_CHAT_MODELS` on `gpt_4o_mini` while `gpt_5_x_mini` exists → upgrade. Prerelease only catches what real users hit if prerelease tracks what real users use. Apply this only to test pins / whitelists, never to prod model defaults.
- **Verify every swap with run-old-then-run-new.** When you update a slug, first run the **old** parametrization once and capture the actual outcome (PASS or FAIL with detail), then run with the **new** slug and capture the outcome. Record both in the report. If both fail in the same way, the swap didn't fix anything — revert and treat the failure as flavor 1. If the old run also passed (newer-sibling upgrade on a green test), the new run must also pass to keep the swap.
- **Document the whole sweep, not just the swaps.** The report's "Model pin sweep" section must list, for every whitelist entry and every hardcoded prerelease slug: what was checked, whether a newer sibling exists, and what action was taken (kept / upgraded / reverted). Zero silent edits and zero silent "looks fine, moving on" calls.
- **Single source of truth for the model list** is `libs/core/kiln_ai/adapters/ml_model_list.py`. When auditing test pins, grep there.
- **Don't auto-commit changes.** Surface them in the report and let the user commit.

---

## Phase 1 — Set up the output directory

```bash
TS=$(date -u +%Y-%m-%dT%H-%M-%SZ)
OUT=".prerelease/${TS}"
mkdir -p "${OUT}"
echo "Writing prerelease results to ${OUT}"
```

`.prerelease/` is gitignored. Keep all log files, raw pytest output, and the final report inside this timestamped folder so re-runs don't clobber prior data.

---

## Phase 2 — Run `checks.sh`

These are not paid but are mandatory for any release. If they fail, the prerelease check fails before we even spend money on API calls.

```bash
uv run ./checks.sh --agent-mode 2>&1 | tee "${OUT}/checks.log"
```

Capture the exit code. If it's non-zero, **don't bail** — keep going with the paid tests so the report covers everything in one pass, but mark the run as failed.

---

## Phase 3 — Run the prerelease pytest set

```bash
uv run python3 -m pytest --runprerelease -v --tb=short \
  -o "addopts=" \
  2>&1 | tee "${OUT}/prerelease.log"
```

Notes:

- `--runprerelease` is registered in the top-level `conftest.py`. It runs only `@pytest.mark.prerelease` tests and implies `--runpaid` for them.
- `-o "addopts="` overrides the project default of `-n auto` (xdist). xdist is incompatible with some of the live-API tests (especially anything that touches global litellm state), so run serially. If a specific test relies on xdist parallelism, override per-invocation.
- This will be slow. Many of the parametrized tests (embeddings across all providers, structured output across providers, streaming across thinking levels) fan out to dozens of cases.
- Tests with missing API keys will `skip`, not fail. Capture skip counts.

If the user wants a faster narrowed run (e.g. only OpenAI + Anthropic checks), use `-k` to filter:

```bash
uv run python3 -m pytest --runprerelease -v --tb=short -o "addopts=" \
  -k "openai or anthropic or vertex" \
  2>&1 | tee "${OUT}/prerelease.log"
```

---

## Phase 4 — Audit the prerelease set itself

This is the housekeeping pass: the test selection itself can rot. Three things to check.

### 4a. Stale model pins in prerelease tests

`ml_model_list.py` only ever grows — entries are marked `deprecated=True`, never removed. So the only stale signals you actually need to look for are:

- Slug's provider entry has `deprecated=True` in `ml_model_list.py` / `ml_embedding_model_list.py`.
- Slug isn't (yet) marked deprecated in our list, but the **provider** returned 4xx / "model not found" during Phase 3's run. (Our curated list trails provider deprecations — being present and non-deprecated is not proof of usability.)
- Slug works fine, but a **newer non-deprecated sibling** in the same family exists in our list. Prerelease should track what real users hit; keeping prerelease pinned at obsolete versions defeats the point. **Always upgrade in this case, even on a fully green run.**

Two places to look:

1. **The whitelist file** — `libs/core/kiln_ai/adapters/pytest_prerelease_whitelist.py`. Every entry must still resolve to a non-deprecated `(model, provider)` in `ml_model_list.py` / `ml_embedding_model_list.py`. Run this check:

```bash
uv run python3 - <<'PYEOF'
from kiln_ai.adapters.ml_model_list import built_in_models
from kiln_ai.adapters.ml_embedding_model_list import built_in_embedding_models
from kiln_ai.adapters.pytest_prerelease_whitelist import (
    PRERELEASE_CHAT_MODELS, PRERELEASE_EMBEDDING_MODELS,
    PRERELEASE_EXTRACTION_MODELS, PRERELEASE_THINKING_MODELS,
)

def chat_status(name, provider):
    for m in built_in_models:
        if m.name == name:
            p = next((p for p in m.providers if p.name.value == provider), None)
            # ml_model_list.py never removes entries, but a model can lose
            # support for a specific provider (NO_PROVIDER) or be marked deprecated.
            return 'NO_PROVIDER' if p is None else ('DEPRECATED' if p.deprecated else 'OK')
    return 'MODEL_REMOVED_OR_RENAMED'  # extremely rare; only happens if the enum changed

def emb_status(name, provider):
    for m in built_in_embedding_models:
        if m.name == name:
            p = next((p for p in m.providers if p.name.value == provider), None)
            return 'NO_PROVIDER' if p is None else 'OK'
    return 'MODEL_REMOVED_OR_RENAMED'

bad = []
for n,p in PRERELEASE_CHAT_MODELS + PRERELEASE_EXTRACTION_MODELS:
    s = chat_status(n,p)
    if s != 'OK': bad.append(('chat', n, p, s))
for n,p in PRERELEASE_EMBEDDING_MODELS:
    s = emb_status(n,p)
    if s != 'OK': bad.append(('embedding', n, p, s))
for prov,name,lvl in PRERELEASE_THINKING_MODELS:
    s = chat_status(name, prov)
    if s != 'OK': bad.append(('thinking', name, prov, s))
if bad:
    for entry in bad: print('STALE:', entry)
else:
    print('All whitelist entries OK')
PYEOF
```

If any entries are stale (deprecated / missing / failed at the provider in Phase 3), **update them in place in `pytest_prerelease_whitelist.py`** — swap to a current model from the same family (latest small variant from the same vendor). This is scoped test-only housekeeping and is exactly what the user expects on a prerelease run.

**Also do a "newer sibling" pass.** For each non-stale whitelist entry, check whether `ml_model_list.py` has a newer member of the same family. Examples:

- `test_connect_vertex_live` is implemented in `app/desktop/studio_server/provider_api.py::connect_vertex`. If its hardcoded probe model is Gemini 2.x and `ml_model_list.py` has Gemini 3, upgrade the probe.
- `PRERELEASE_CHAT_MODELS` entry on `gpt_4o_mini` — is `gpt_5_x_mini` available? Move forward.
- `PRERELEASE_CHAT_MODELS` entry on `claude_sonnet_4_5` — is `claude_sonnet_4_6` / `4_7` available? Move forward.
- `PRERELEASE_EXTRACTION_MODELS` entry on an older multimodal model — is there a newer multimodal-capable model from the same vendor? Move forward.

Rule of thumb: if `ml_model_list.py` ordering puts a newer sibling above the current pin, upgrade. If unsure, ask the user; don't churn aggressively.

**Verify every swap with run-old-then-run-new.** Before you accept any swap, run the test under the old slug and capture the actual result, then run under the new slug and capture the result. Record both in the report. If both fail with the same error, the swap accomplished nothing — **revert it and reclassify as flavor 1** (real failure to investigate).

```bash
# Pattern for a single test that you're about to swap:
uv run python3 -m pytest --runprerelease -v --tb=short -o "addopts=" \
  "<path>::<test_name>[<old-param-id>]" 2>&1 | tee "${OUT}/swap_<slug>_before.log"
# … edit the whitelist / parametrize to the new slug …
uv run python3 -m pytest --runprerelease -v --tb=short -o "addopts=" \
  "<path>::<test_name>[<new-param-id>]" 2>&1 | tee "${OUT}/swap_<slug>_after.log"
```

2. **Per-test hardcoded slugs**. The most likely culprit is `libs/core/kiln_ai/adapters/test_prompt_adaptors.py::test_openrouter`, which has a long parametrized list including `gemini_1_5_*` family members and other older slugs.

Find all hardcoded model strings inside prerelease-marked tests:

```bash
uv run python3 -m pytest --runprerelease --collect-only -q -o "addopts=" \
  2>&1 | grep '::' | awk -F'::' '{print $1}' | sort -u > "${OUT}/prerelease_test_files.txt"
```

For each file in `prerelease_test_files.txt`, grep model slugs and cross-reference against `ml_model_list.py`:

```bash
# Pull the canonical set of current model enum values
grep -oE '^[[:space:]]+[a-z][a-z0-9_]+ = "[a-z0-9_]+"' \
  libs/core/kiln_ai/adapters/ml_model_list.py | \
  awk -F'"' '{print $2}' | sort -u > "${OUT}/current_model_ids.txt"

# Now manually scan each prerelease test file for string literals
# that look like model IDs but aren't in current_model_ids.txt.
```

Treat any pinned slug **not** in the current model list as a candidate for housekeeping. **Update the test** (replace the dead slug with a current model from the same family), as long as it's clearly a "we hardcoded a slug we were too lazy to revisit" situation. If the slug is being asserted for some specific reason (e.g., testing legacy behavior), leave it alone and flag it.

Common families to map old → new:
- `gemini_1_5_*` → `gemini_2_5_*` or `gemini_3_*` (check `ml_model_list.py` for current available).
- `claude_3_5_*` → `claude_sonnet_4_*` / `claude_opus_4_*` / `claude_4_5_haiku`.
- `llama_3_1_*`, `llama_3_2_*` → `llama_3_3_70b` / `llama_4_*` (only if the test isn't specifically about the older model).
- `nemotron_70b` → `nemotron_3_*`.

### 4b. Coverage gaps

The prerelease set should cover, at minimum:

| Area | Test(s) |
|---|---|
| Vertex live connect | `app/desktop/studio_server/test_provider_api.py::test_connect_vertex_live` |
| OpenAI basic call | `libs/core/kiln_ai/adapters/test_prompt_adaptors.py::test_openai` |
| Anthropic via OpenRouter / Anthropic API | `test_structured_output_anthropic_*`, `test_structured_output_openrouter_function_calling_nested_object` |
| Gemini API | covered via embeddings + prompt caching + thinking levels |
| Groq | `test_groq` |
| OpenRouter multi-model | `test_openrouter[...]` (parametrized) |
| Amazon Bedrock | `test_amazon_bedrock` |
| Embedding API (whitelist) | `test_paid_generate_embeddings_basic_prerelease_smoke`, `test_generate_embedding_prerelease_smoke` |
| Custom-dimension embeddings (whitelist) | `test_paid_generate_embeddings_custom_dimensions_prerelease_smoke`, `test_generate_embedding_with_user_supplied_dimensions_prerelease_smoke` |
| Structured output (json_schema, function_calling, flat/nested/array) | `test_structured_output_*` |
| Streaming (OpenAI protocol + AI SDK protocol) | `test_invoke_openai_stream_chunks`, `test_invoke_ai_sdk_stream` |
| Tool calling | `test_tools_gpt_4_1_mini` |
| Thinking-level reasoning (whitelist) | `test_thinking_level_reasoning_content_prerelease_smoke` |
| Reranker | `test_reranker_integration_success` |
| Document extraction (whitelist of models × probe mime types) | `test_extract_document_success_prerelease_smoke`, `test_provider_bad_request_prerelease_smoke` |
| Semantic chunker (real embedding integration) | `test_semantic_chunker_real_integration` |
| Fireworks fine-tune | `test_fetch_all_deployments` |
| Prompt caching (Anthropic + OpenAI + Gemini + Fireworks + Together) | `test_prompt_caching_cache_hit` |

If you find a new provider/family in `ml_model_list.py` that isn't represented in the prerelease set — flag it. (Don't add new tests unsolicited; propose the gap in the report and let the user decide.)

### 4c. New paid tests that should arguably be prerelease

List recently added `@pytest.mark.paid` tests that are *not* `@pytest.mark.prerelease`-tagged, so the user can decide if any should be promoted:

```bash
# all paid test locations
grep -rn "@pytest.mark.paid" --include="*.py" | awk -F: '{print $1":"$2}' > "${OUT}/paid_tests.txt"
# all prerelease test locations
grep -rn "@pytest.mark.prerelease" --include="*.py" | awk -F: '{print $1":"$2}' > "${OUT}/prerelease_tests.txt"
# show paid tests that are NOT prerelease, sorted by recency
diff <(sort "${OUT}/paid_tests.txt") <(sort "${OUT}/prerelease_tests.txt") | \
  grep '^<' > "${OUT}/paid_only.txt"
git log --since="3 months ago" --diff-filter=AM --name-only --pretty=format: -- \
  $(awk -F: '{print $1}' "${OUT}/paid_only.txt" | sort -u) | sort -u | \
  head -50 > "${OUT}/recent_paid_files.txt"
```

In the report, list the few files in `recent_paid_files.txt` and ask the user whether any of their tests are prerelease-worthy.

### 4d. Prod-code model probes (flag for user, don't edit)

Some prod-code paths hardcode a model slug as a **probe** — a narrow connectivity / auth check where the model is just a vehicle to hit the API, not a feature the user picked. Today the canonical example is `app/desktop/studio_server/provider_api.py::connect_vertex`, which calls `litellm.acompletion(model="vertex_ai/gemini-X.Y-flash", …)` to verify the user's Vertex credentials when they click "Connect" in the UI.

Probes like this should be **kept on the latest available model in their family**, otherwise the Connect button quietly drifts toward calling a deprecated/removed model. But **this skill never edits prod code directly** — it flags the situation in the report so the user can decide and make the change.

How to tell a probe from real prod-path code:

- ✅ Probe: a connectivity / auth check whose only job is to issue a tiny request to see if credentials work. The model choice is incidental; any current model from the same family would work.
- ❌ Not a probe: code where the model is part of the user-visible behavior (defaults the user could see, fine-tune flows, eval scoring, etc.). Leave these alone — they're flavor 1 if broken.

#### Sweep

Grep for any hardcoded inference-probe slugs that target a vendor model directly (string with `gemini`/`gpt`/`claude`/`llama`, inside a `model="…"` kwarg, in non-test prod files):

```bash
grep -rnE 'model=["'\''][^"'\'']*((gemini|gpt|claude|llama)[^"'\'']*)["'\''']' \
  app/desktop libs/core/kiln_ai libs/server/kiln_server \
  --include="*.py" 2>/dev/null \
  | grep -v "test_" | grep -v "/build/" \
  | tee "${OUT}/prod_probes.txt"
```

For each hit:

1. Confirm it's a probe (see ✅ / ❌ above). If you're not sure, treat it as not a probe.
2. Check `ml_model_list.py` for the newest non-deprecated member of the same family at that provider (e.g. for `vertex_ai/gemini-X.Y-flash`, find the highest-versioned `gemini_*_flash` with a non-deprecated vertex provider entry).
3. Record the finding in the report's "Prod-code probe sweep" table: file:line, current slug, suggested newer slug (or "none — already latest"), and the verifying live test (e.g. `test_connect_vertex_live`).
4. **Do not edit prod code.** Leave the decision to the user. The verdict line at the end of the run should call out any flagged probes explicitly.

If the prerelease test that exercises a probe fails outright (e.g. `test_connect_vertex_live` returns 4xx), that's a flavor-1 failure — list it under "Failures" in addition to flagging the probe.

Every grep hit goes in the sweep table even when no newer sibling exists (`Suggested` = "none"). Silent "looks fine" is not allowed.

---

## Phase 5 — Write the report

Create `.prerelease/<timestamp>/REPORT.md` with these sections:

```markdown
# Kiln Prerelease Check — <timestamp>

## Summary
- Overall: PASS / FAIL / PASS WITH GAPS
- checks.sh: <pass|fail>
- prerelease pytest: <N passed, M failed, K skipped>
- Audit findings: <count of stale pins>, <count of coverage gaps>

## Failures
For each failure:
- Test ID
- Provider
- Failure flavor: regression OR test-housekeeping
- Excerpt of the relevant stderr / assertion
- Recommended action (do not silently patch prod code)

## Skipped tests (missing credentials)
List by provider so the user can decide what keys to add.

## Model pin sweep (mandatory, every run)
Full table of every hardcoded slug in prerelease whitelists / parametrize lists, what was checked, and what was done. Even on a green run this section is required — silent "looks fine" is not allowed.

| Location (file:line) | Current slug | `ml_model_list.py` status | Newer sibling? | Action |
|---|---|---|---|---|
| `…/pytest_prerelease_whitelist.py:NN` | `claude_sonnet_4_5` | OK, not deprecated | yes — `claude_sonnet_4_6` | upgraded (see Test updates applied) |
| `…/pytest_prerelease_whitelist.py:NN` | `gpt_4o_mini` | OK, not deprecated | no (still the latest mini) | kept |
| `…/test_prompt_adaptors.py:NN` | `phi_3_5` (openrouter) | provider entry deprecated=True | n/a (deprecated) | upgraded to `phi_4` (see Test updates applied) |

`ml_model_list.py status` is one of: `OK`, `deprecated`, `no-provider-entry`. `Newer sibling?` says yes/no and names the candidate. `Action` is `kept` or `upgraded`.

## Stale pins not auto-fixed
Cases where you spotted staleness but did NOT swap (you weren't confident, the family map is ambiguous, or it crosses into prod-path territory). For each: file:line, current slug, suggested replacement, reason for deferring.

## Coverage gaps
- New providers in ml_model_list.py with no prerelease test
- Recently added paid tests not in the prerelease set (with a one-line rationale for why each MIGHT be prerelease-worthy)

## Test updates applied (housekeeping, scoped to test files / whitelist only)
Every test/whitelist swap goes here with both run outcomes. One row per swap:

| File:line | Old slug | New slug | Reason | Old run | New run |
|---|---|---|---|---|---|
| `…/pytest_prerelease_whitelist.py:NN` | `claude_sonnet_4_5` | `claude_sonnet_4_6` | newer-sibling-available | PASS | PASS |
| `…/test_prompt_adaptors.py:NN` | `phi_3_5` | `phi_4` | deprecated-in-our-list | FAIL (provider 404) | PASS |

`Reason` is one of: `provider-rejected` (4xx at provider), `deprecated-in-our-list`, `newer-sibling-available`. `Old run` and `New run` are both required — they prove the swap actually changed behavior (or that an upgrade-on-green stayed green). If both columns say FAIL, **the swap should have been reverted** — explain why it wasn't in a row below the table.

## Prod-code probe sweep (flag for user review — no edits)
Mandatory every run. Lists every hardcoded inference-probe model slug found in prod code (Phase 4d). The skill does NOT edit prod code; this section is the artifact the user reads to decide whether to bump a probe.

| File:line | Current slug | Suggested newer slug | Verifying test | Verifying test result | Notes |
|---|---|---|---|---|---|
| `app/desktop/studio_server/provider_api.py:NNNN` | `vertex_ai/gemini-3.5-flash` | `vertex_ai/gemini-3.X-flash` (from `ml_model_list.py`) | `test_connect_vertex_live` | PASS | current probe still works; newer family member available |
| `path/to/file.py:NN` | `…` | none — already latest | `test_…` | PASS | no action needed |

`Suggested newer slug` is "none — already latest" if `ml_model_list.py` doesn't have a newer non-deprecated sibling at that provider. If the verifying live test failed, also list it under "Failures" — that's a flavor-1 signal regardless of whether a newer slug is available.

If a grep hit looks like real prod-path behavior rather than a probe, record it under "Flagged for user review" below — do not include it in this table.

## Flagged for user review
Things you noticed (test pins you weren't confident to swap, prod-path code that isn't a probe, suspicious failures you couldn't safely touch) that the user should look at. Each row: file:line, what's stale/suspicious, why you didn't change it.

## Suggested next steps
What the user should do before tagging the release.
```

Keep the report scan-readable. Lead with the verdict. Don't bury failures.

---

## Phase 6 — Hand back to the user

Print the path to the report and a one-line verdict:

```bash
echo "Prerelease check complete. Report: ${OUT}/REPORT.md"
```

Then summarize the verdict in chat (one or two sentences):

- If everything passed: `Prerelease check: PASS. <N> tests passed, <K> skipped (missing keys: <providers>). Report at <path>.`
- If anything failed: `Prerelease check: FAIL. <X> tests failed across <providers>. See <path>/REPORT.md before tagging.`
- If the only "failures" are stale pins that you've fixed: `Prerelease check: PASS WITH HOUSEKEEPING. Updated <N> stale model pins; no prod code touched. Report at <path>.`

---

## Checklist

- [ ] `.prerelease/<timestamp>/` directory created
- [ ] `checks.sh --agent-mode` run, log captured
- [ ] `--runprerelease` pytest run, log captured
- [ ] "Model pin sweep" table filled out for **every** whitelist entry and every hardcoded prerelease slug — including the ones that were kept (silent "looks fine" not allowed)
- [ ] Newer-sibling upgrades applied even when the old slug was green
- [ ] Every applied test/whitelist swap verified with run-old-then-run-new, both outcomes in the "Test updates applied" table
- [ ] Phase 4d prod-probe sweep done; every grep hit listed in the "Prod-code probe sweep" table with `Suggested newer slug` (or "none — already latest")
- [ ] Coverage-gap audit done (Phase 4b + 4c)
- [ ] No prod source code was modified (probe bumps left for the user to apply)
- [ ] `REPORT.md` written with verdict, sweep table, swaps, probe table, failures, skips, gaps
- [ ] Verdict surfaced to the user with the report path; any probe with a newer suggested slug called out explicitly
