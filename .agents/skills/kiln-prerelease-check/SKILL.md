---
name: kiln-prerelease-check
description: Run the Kiln pre-release smoke test suite plus the standard CI checks (checks.sh), diagnose every prerelease test that broke (and why), and write a clean readable report with recommended actions. Read-only — it never edits code. Use when the user wants to validate a release candidate, run prerelease tests, or asks for a "prerelease check / smoke / audit".
---

# Kiln Pre-release Check

End-to-end pre-release verification and **diagnosis**. This skill:

1. Runs the standard CI checks (`checks.sh` — lint / format / typecheck / unit tests).
2. Runs the curated `@pytest.mark.prerelease` smoke set (real, paid API calls).
3. For every test that broke, works out **what** broke and **why** — including whether the cause is a model that's gone deprecated (per `ml_model_list.py`) or that the provider no longer recognizes the slug.
4. Sweeps the prerelease model pins for staleness and newer model versions.
5. Writes a clean, scan-readable report with a clear **recommended action** for each finding.

**This skill is read-only. It does not change any code, tests, whitelists, or prod source — ever.** Its entire output is a report at `.prerelease/<timestamp>/REPORT.md` (this directory is gitignored). When the right action is to bump a model pin or update the whitelist, the report *recommends* it; the user makes the change.

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

This whitelist is the thing most likely to go stale, so it's the main target of the pin sweep in Phase 4. The fan-out tests (e.g. `test_extract_document_success` over every model × mime type, `test_paid_generate_embeddings_basic` over every embedding) are **only `@pytest.mark.paid`** — not `@pytest.mark.prerelease` — and are out of scope for this skill.

---

## Global rules

- **Read-only. Make no edits.** Do not modify test files, the whitelist, prod source, config, or anything else. Every actionable finding is a *recommendation* in the report. If you catch yourself about to call Edit/Write on anything other than files under `.prerelease/<timestamp>/`, stop.
- **Network access is required.** Every test phase makes real API calls or hits remote model-list endpoints. If you are running this skill inside a sandboxed Bash session, request `required_permissions: ["all"]` for the test commands.
- **Env vars:** Source `.env` before running anything that needs API keys:
  ```bash
  export $(grep -v '^#' .env | xargs)
  ```
  Provider-specific env vars the prerelease set may touch: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `GROQ_API_KEY`, `OPENROUTER_API_KEY`, `FIREWORKS_API_KEY`, `TOGETHER_API_KEY`, `SILICONFLOW_CN_API_KEY`, `COHERE_API_KEY`, `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY`, plus `KILN_TEST_VERTEX_PROJECT_ID` (+ optional `KILN_TEST_VERTEX_LOCATION`) for the Vertex live check, which also requires `gcloud auth application-default login` against a project with `aiplatform.googleapis.com` enabled.
- **A missing key is a coverage gap, not a failure.** Each missing key makes the relevant test `pytest.skip(...)`. That isn't a prerelease failure — surface it in the report so the user can decide whether to provide the key and re-run.
- **`ml_model_list.py` never deletes entries — it only marks them `deprecated=True`.** So a slug missing from our list is not a signal you'll normally encounter. The signals that matter when diagnosing a break or staleness are:
  1. The provider entry has `deprecated=True` in our list.
  2. The provider itself rejects the slug at runtime (4xx / "model not found") — note our list trails provider deprecations, so this can happen *before* we've marked it deprecated. This is how you'd discover a model "no longer exists" even when our list still lists it.
  3. A newer non-deprecated sibling in the same family now exists in our list, regardless of whether the current pin still works.
- **Single source of truth for the model list** is `libs/core/kiln_ai/adapters/ml_model_list.py` (chat) and `ml_embedding_model_list.py` (embeddings). Cross-reference there when diagnosing.
- **The pin sweep is mandatory, not "only when something fails."** Even on a fully green run, every hardcoded slug in `pytest_prerelease_whitelist.py` and in prerelease test parametrize lists must be cross-checked against the model list and reported (kept-and-current vs. has-newer-sibling vs. deprecated). Zero silent "looks fine, moving on" calls.

---

## Phase 1 — Set up the output directory

```bash
TS=$(date -u +%Y-%m-%dT%H-%M-%SZ)
OUT=".prerelease/${TS}"
mkdir -p "${OUT}"
echo "Writing prerelease results to ${OUT}"
```

`.prerelease/` is gitignored. Keep all log files, raw pytest output, and the final report inside this timestamped folder so re-runs don't clobber prior data. This folder is the **only** place this skill writes.

---

## Phase 2 — Run `checks.sh`

These are not paid but are mandatory for any release. If they fail, the prerelease check fails before we even spend money on API calls.

```bash
uv run ./checks.sh --agent-mode 2>&1 | tee "${OUT}/checks.log"
```

Capture the exit code. If it's non-zero, **don't bail** — keep going with the paid tests so the report covers everything in one pass, but mark the overall run as failed.

---

## Phase 3 — Run the prerelease pytest set

```bash
uv run python3 -m pytest --runprerelease -v --tb=short \
  -o "addopts=" \
  2>&1 | tee "${OUT}/prerelease.log"
```

Notes:

- `--runprerelease` is registered in the top-level `conftest.py`. It runs only `@pytest.mark.prerelease` tests and implies `--runpaid` for them.
- `-o "addopts="` overrides the project default of `-n auto` (xdist). xdist is incompatible with some of the live-API tests (especially anything that touches global litellm state), so run serially.
- This will be slow. Many of the parametrized tests fan out to dozens of cases.
- Tests with missing API keys will `skip`, not fail. Capture skip counts.

If the user wants a faster narrowed run (e.g. only OpenAI + Anthropic), use `-k` to filter:

```bash
uv run python3 -m pytest --runprerelease -v --tb=short -o "addopts=" \
  -k "openai or anthropic or vertex" \
  2>&1 | tee "${OUT}/prerelease.log"
```

---

## Phase 4 — Diagnose

This is where the skill earns its keep: for every failure, explain the cause; for every pin, report staleness. No edits — only findings and recommendations.

### 4a. Diagnose each failure (what broke, why, recommended action)

For every test that did **not** pass in Phase 3, build one finding. Walk the failure through this decision tree to land on a cause and a recommended action:

1. **Missing credentials → skip, not failure.** (`pytest.skip` for absent key.) Don't list under failures; list under "Skipped tests". Recommended action: add the key and re-run if that coverage matters.
2. **Provider rejected the model slug** — error mentions `model not found`, `does not exist`, `404`, `model_not_found`, `invalid model`, decommissioned, etc. Cross-reference the slug against `ml_model_list.py`:
   - If our list marks that provider entry `deprecated=True` → cause: **deprecated model, provider has dropped it**. Recommended action: bump the pin/whitelist to the newest non-deprecated sibling in the same family (name the candidate).
   - If our list still lists it as non-deprecated → cause: **model no longer exists at the provider; our list trails reality**. Recommended action: (a) bump the test pin/whitelist to a current sibling, and (b) flag that `ml_model_list.py` should mark this entry `deprecated=True`. Name both.
3. **Auth / quota / rate-limit / transient network** — 401/403/429/5xx, timeouts. Cause: environment or provider-side, not our code. Recommended action: check the key/quota and re-run; only escalate if it reproduces.
4. **Behavioral assertion mismatch** — the call succeeded but the response shape, content, token/cache fields, streaming chunks, or reasoning output changed. Cause: **provider changed behavior we depend on (real regression)**. Recommended action: investigate the prod path that relies on this; do not assume it's a stale pin. This is the highest-signal failure class — call it out prominently.
5. **Our-code error** — traceback originates in `libs/core` / `app/` rather than the provider response. Cause: **regression in Kiln**. Recommended action: investigate the implicated code; name the file/function from the traceback.

If you can't confidently distinguish a stale-pin cause (2) from a real regression (4 or 5), **report it as a possible regression** and say what additional check would disambiguate (e.g. "try the same call with a current sibling slug to see if it's the model or the code"). Never recommend a silent pin bump for an ambiguous failure.

Record, per failure: test ID · provider · cause class · the model slug involved (if any) and its `ml_model_list.py` status · a short excerpt of the actual error · recommended action.

### 4b. Model-pin staleness sweep (mandatory every run, even when green)

Independent of failures, every hardcoded model slug the prerelease set depends on must be checked against the model list and reported. A pin can be perfectly green today and still be worth bumping because a newer sibling shipped — prerelease only catches what real users hit if it tracks what real users actually use.

**In scope (check these every run):**
- Every entry in `libs/core/kiln_ai/adapters/pytest_prerelease_whitelist.py`.
- Hardcoded model slugs inside the body or parametrize list of any `@pytest.mark.prerelease` test (notably `libs/core/kiln_ai/adapters/test_prompt_adaptors.py::test_openrouter`).

**Out of scope (don't report as stale):**
- Hardcoded slugs in mock-only unit tests (no `@pytest.mark.paid` / `@pytest.mark.prerelease`) — the slug is a label, no real call happens.
- Slugs in fixtures, recorded VCR cassettes, snapshot files.
- Slugs in `@pytest.mark.paid` tests that aren't also `@pytest.mark.prerelease`.

**Step 1 — status of each whitelist entry.** Run:

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
            return 'NO_PROVIDER' if p is None else ('DEPRECATED' if p.deprecated else 'OK')
    return 'MODEL_REMOVED_OR_RENAMED'

def emb_status(name, provider):
    for m in built_in_embedding_models:
        if m.name == name:
            p = next((p for p in m.providers if p.name.value == provider), None)
            return 'NO_PROVIDER' if p is None else 'OK'
    return 'MODEL_REMOVED_OR_RENAMED'

print('== chat / extraction ==')
for n,p in PRERELEASE_CHAT_MODELS + PRERELEASE_EXTRACTION_MODELS:
    print(f'{chat_status(n,p):>22}  {n}  ({p})')
print('== embedding ==')
for n,p in PRERELEASE_EMBEDDING_MODELS:
    print(f'{emb_status(n,p):>22}  {n}  ({p})')
print('== thinking ==')
for prov,name,lvl in PRERELEASE_THINKING_MODELS:
    print(f'{chat_status(name,prov):>22}  {name}  ({prov}, level={lvl})')
PYEOF
```

Anything not `OK` is stale and goes in the sweep table with a recommended replacement (newest non-deprecated sibling in the same family).

**Step 2 — newer-sibling pass for the `OK` entries.** For each entry that's `OK`, scan `ml_model_list.py` for a newer member of the same family. List the canonical model ids to compare against:

```bash
grep -oE '^[[:space:]]+[a-z][a-z0-9_]+ = "[a-z0-9_]+"' \
  libs/core/kiln_ai/adapters/ml_model_list.py | \
  awk -F'"' '{print $2}' | sort -u > "${OUT}/current_model_ids.txt"
```

Examples of the judgment call:
- `PRERELEASE_CHAT_MODELS` on `gpt_4o_mini` while `gpt_5_x_mini` exists → recommend bump.
- `PRERELEASE_CHAT_MODELS` on `claude_sonnet_4_5` while `claude_sonnet_4_6`/`4_7` exists → recommend bump.
- `gemini_1_5_*` → `gemini_2_5_*` / `gemini_3_*`; `claude_3_5_*` → `claude_sonnet_4_*` / `claude_4_5_haiku`; `llama_3_x` → `llama_3_3_70b` / `llama_4_*`.

Rule of thumb: if `ml_model_list.py` ordering puts a newer sibling above the current pin, recommend the bump. If it's genuinely ambiguous which sibling is "current", say so and let the user pick — don't assert a churny recommendation.

**Step 3 — per-test hardcoded slugs.** Enumerate the prerelease test files and scan them for slugs not in `current_model_ids.txt`:

```bash
uv run python3 -m pytest --runprerelease --collect-only -q -o "addopts=" \
  2>&1 | grep '::' | awk -F'::' '{print $1}' | sort -u > "${OUT}/prerelease_test_files.txt"
```

Cross-reference each pinned slug against `current_model_ids.txt` and the deprecation status. Report any obsolete pins as recommendations.

Every in-scope pin lands in the sweep table — including the ones that are current and need no action. Silent omission is not allowed.

### 4c. Coverage gaps

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

If a new provider/family in `ml_model_list.py` isn't represented in the prerelease set, note the gap as a recommendation.

Also list recently added `@pytest.mark.paid` tests that are *not* `@pytest.mark.prerelease`-tagged, so the user can decide if any should be promoted:

```bash
grep -rn "@pytest.mark.paid" --include="*.py" | awk -F: '{print $1":"$2}' > "${OUT}/paid_tests.txt"
grep -rn "@pytest.mark.prerelease" --include="*.py" | awk -F: '{print $1":"$2}' > "${OUT}/prerelease_tests.txt"
diff <(sort "${OUT}/paid_tests.txt") <(sort "${OUT}/prerelease_tests.txt") | grep '^<' > "${OUT}/paid_only.txt"
git log --since="3 months ago" --diff-filter=AM --name-only --pretty=format: -- \
  $(awk -F: '{print $1}' "${OUT}/paid_only.txt" | sort -u) | sort -u | head -50
```

### 4d. Prod-code model probes (flag only)

Some prod-code paths hardcode a model slug as a **probe** — a narrow connectivity/auth check where the model is just a vehicle to hit the API, not a feature the user picked. The canonical example is `app/desktop/studio_server/provider_api.py::connect_vertex`, which calls `litellm.acompletion(model="vertex_ai/gemini-X.Y-flash", …)` to verify Vertex credentials when the user clicks "Connect".

These should stay on the latest available model in their family, otherwise the Connect button drifts toward a deprecated/removed model. **This skill only flags them** — it does not edit prod code, and the recommendation in the report is the artifact the user acts on.

Sweep for hardcoded inference-probe slugs in non-test prod files:

```bash
grep -rnE 'model=["'\''][^"'\'']*((gemini|gpt|claude|llama)[^"'\'']*)["'\''']' \
  app/desktop libs/core/kiln_ai libs/server/kiln_server \
  --include="*.py" 2>/dev/null \
  | grep -v "test_" | grep -v "/build/" \
  | tee "${OUT}/prod_probes.txt"
```

For each hit:
1. Decide whether it's a probe (connectivity/auth check, model incidental) or real prod behavior (a default the user sees, fine-tune flow, eval scoring). If unsure, treat it as real prod behavior.
2. For probes, check `ml_model_list.py` for the newest non-deprecated sibling at that provider.
3. Record in the probe table: file:line · current slug · suggested newer slug (or "none — already latest") · the verifying live test and its result.

Every grep hit goes in the table even when no newer sibling exists. If the verifying live test failed outright, also list it under Failures (it's a real-failure signal).

---

## Phase 5 — Write the report

Create `.prerelease/<timestamp>/REPORT.md`. Lead with the verdict; make every finding skim-readable with an explicit recommended action. This is the only artifact the skill produces.

```markdown
# Kiln Prerelease Check — <timestamp>

## Verdict
- Overall: PASS / FAIL / PASS WITH RECOMMENDATIONS
- checks.sh: <pass|fail>
- prerelease pytest: <N passed, M failed, K skipped>
- Headline: <one sentence — the single most important thing the user must know before tagging>

## Failures — what broke, why, and what to do
One block per failing test. Sorted most-actionable first (real regressions before stale pins).

### <test ID>
- Provider: <provider>
- Cause: <deprecated model | model no longer exists at provider | provider behavior change (regression) | Kiln code regression | auth/quota/transient>
- Model slug: <slug> — `ml_model_list.py` status: <OK | deprecated | no-provider-entry | n/a>
- Evidence: <short excerpt of the actual error / failed assertion>
- Recommended action: <concrete next step — e.g. "bump PRERELEASE_CHAT_MODELS pin from X to Y (newest sibling)"; or "investigate prod path Z — response shape changed"; or "mark this entry deprecated=True in ml_model_list.py and bump the pin". Recommendation only — this skill makes no edits.>

## Skipped tests (missing credentials)
List by provider, with which env var is missing, so the user can decide what to add and re-run.

## Model-pin staleness sweep (mandatory, every run)
Every in-scope hardcoded slug — including current ones needing no action.

| Location (file:line) | Current slug | `ml_model_list.py` status | Newer sibling? | Recommendation |
|---|---|---|---|---|
| `…/pytest_prerelease_whitelist.py:NN` | `claude_sonnet_4_5` | OK | yes — `claude_sonnet_4_6` | bump to `claude_sonnet_4_6` |
| `…/pytest_prerelease_whitelist.py:NN` | `gpt_4o_mini` | OK | no | keep (current) |
| `…/test_prompt_adaptors.py:NN` | `gemini_1_5_flash` (openrouter) | deprecated | n/a | bump to `gemini_2_5_flash` |

`status` ∈ {OK, deprecated, no-provider-entry, removed/renamed}. `Recommendation` ∈ {keep (current), bump to <slug>, investigate}.

## Prod-code probe sweep (flag only — no edits)
Every hardcoded inference-probe slug found in prod code (Phase 4d).

| File:line | Current slug | Suggested newer slug | Verifying test | Test result | Notes |
|---|---|---|---|---|---|
| `app/desktop/studio_server/provider_api.py:NNNN` | `vertex_ai/gemini-2.5-flash` | `vertex_ai/gemini-3-flash` | `test_connect_vertex_live` | PASS | probe still works; newer family member exists |
| `path/to/file.py:NN` | `…` | none — already latest | `test_…` | PASS | no action |

## Coverage gaps
- Providers/families in `ml_model_list.py` with no prerelease test.
- Recently added paid tests not in the prerelease set (one line each on why it MIGHT be prerelease-worthy).

## Flagged for user review
Anything you noticed but couldn't safely classify: ambiguous failures (model-vs-code unclear), prod-path code that isn't a probe, suspicious behavior. Each row: file:line / test · what's suspicious · what would disambiguate.

## Suggested next steps
Ordered checklist of what the user should do before tagging the release (apply recommended pin bumps, investigate regression X, add key for skipped provider Y, etc.).
```

Keep it scan-readable. Lead with the verdict. Don't bury real regressions under pin-housekeeping.

---

## Phase 6 — Hand back to the user

Print the report path and a one-line verdict:

```bash
echo "Prerelease check complete. Report: ${OUT}/REPORT.md"
```

Then summarize in chat (one or two sentences):

- All green, nothing stale: `Prerelease check: PASS. <N> passed, <K> skipped (missing keys: <providers>). No stale pins. Report at <path>.`
- Green but recommendations exist: `Prerelease check: PASS WITH RECOMMENDATIONS. <N> passed; <M> stale/older pins to consider bumping (no changes made). Report at <path>.`
- Something failed: `Prerelease check: FAIL. <X> failed across <providers> — <one-line dominant cause>. See <path>/REPORT.md before tagging.`

Remember: the skill never made any edits. If the report recommends pin bumps or a prod-probe change, those are for the user to apply.

---

## Checklist

- [ ] `.prerelease/<timestamp>/` directory created (the only place anything was written)
- [ ] `checks.sh --agent-mode` run, log captured
- [ ] `--runprerelease` pytest run, log captured
- [ ] Every failure diagnosed with a cause class and a concrete recommended action (regression vs. deprecated-model vs. model-gone vs. auth/transient)
- [ ] Model-pin staleness sweep table filled for **every** in-scope slug, including current ones needing no action
- [ ] Newer-sibling recommendations included even for green pins
- [ ] Prod-probe sweep done; every grep hit in the probe table with a suggested slug (or "none — already latest")
- [ ] Coverage-gap audit done
- [ ] Skipped tests listed by provider + missing env var
- [ ] **No files edited outside `.prerelease/<timestamp>/`** — all fixes are recommendations
- [ ] `REPORT.md` written, verdict first, recommended actions explicit
- [ ] Verdict surfaced to the user with the report path
