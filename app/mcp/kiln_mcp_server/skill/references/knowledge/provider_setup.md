---
name: provider_setup
description: |
  Provider and API key setup help for non-technical users. Loaded by Project Operations mode and Learn About Kiln mode when users need help connecting AI services.
---
# Provider Setup & API Key Help

Reference knowledge for helping users who are stuck connecting AI providers (the API key screen). Many users are non-technical — they may not know what an API key is, and their IT or engineering team may be responsible for API access and billing.

## Knowledge Required


## API Docs

Load the relevant endpoint doc **before** making each API call. For provider and model wiring, scan `references/knowledge/api_docs/providers_models_api_list.md` first.

| Endpoint | Load |
|----------|------|
| **Catalog:** Providers & Models API | `references/knowledge/api_docs/providers_models_api_list.md` |
| **Catalog:** Settings & Utilities API | `references/knowledge/api_docs/settings_utilities_api_list.md` |
| **Catalog:** Run Configs API | `references/knowledge/api_docs/run_configs_api_list.md` |
| POST connect Ollama | `references/knowledge/api_docs/post_api_provider_ollama_connect.md` |
| POST connect Docker Model Runner | `references/knowledge/api_docs/post_api_provider_docker_model_runner_connect.md` |
| GET settings available providers | `references/knowledge/api_docs/get_api_settings_available_providers.md` |
| GET run configs (infer providers) | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_run_configs.md` |
| GET available models (verify provider) | `references/knowledge/api_docs/get_api_available_models.md` |

## Reading Connectivity State

When the user asks which providers they have connected (or implies it — e.g. while filtering model recommendations to "available" / "connected" providers), use the canonical sources below. Do **not** guess at `/api/providers`, `/api/settings/connectors`, or `/api/settings` endpoints; none exist.

- **In Project Operations / Improve Task mode** (after the `agent_overview` bootstrap): `agent_overview.connected_providers` is the canonical workspace-wide map. Shape: `{provider_id: {connected: true|false}}`. **Workspace-wide means every provider with a valid API key globally — NOT filtered to the current task.** Re-using the snapshot already in context is correct; do not re-fetch from a separate provider endpoint.
- **No task loaded** (Learn About Kiln, freeform questions): `GET /api/available_models` with `jq_filter="[.[] | .provider_id] | unique"` (load `references/knowledge/api_docs/get_api_available_models.md` first). This is the runtime endpoint — only providers with working credentials appear, so it doubles as a credential-validity check.

### Configured vs connected — keep the sets distinct

- `agent_overview.run_configs[].model_provider` = providers **configured for this task** (a subset of connected).
- `agent_overview.connected_providers` = providers **connected to the workspace overall**.

The configured set is always a subset of the connected set. They collapse only by coincidence — when every connected provider happens to have at least one run_config in this task. Do not treat `run_configs[].model_provider` as a proxy for connectivity in either direction:

- *Over-counting trap (collapse to superset):* answering "which providers do I have connected?" by enumerating run_configs implies the configured set is the workspace-wide set. It isn't.
- *Under-counting trap (shortcut to subset):* declaring "only `<X>` is connected" because every run_config in this task uses `<X>` ignores the rest of the workspace's connected providers. The connected set may be much wider.

When answering a connectivity question — or filtering model recommendations to connected providers — surface the distinction explicitly: *"this task's run configs use these N providers; your workspace has M providers connected overall."* Never imply the two sets are the same without checking.

Do **not** confuse `available_models` (runtime: providers with working credentials) with `available_providers` (catalog: every provider Kiln supports, with or without credentials). The connectivity-state question is answered by the former, never the latter.

## Provider Setup Approaches

**TypeSafe AI:** the standard API-key flow (key from the user's TypeSafe AI console; the connect dialog links to it). Its Jev models are classification-only; load `references/knowledge/typesafe_jev.md` before recommending them.

> **Which path do I start on?** Error symptom (user reports "not working", timeout, 429, 401, or unexpected model behavior) → start at **Diagnose First** below. Fresh setup or adding a new provider (no error symptom) → skip to **Approach for first-time setup** further down.

### Diagnose First (for error-symptom prompts)

When the user reports an error (timeout, 429, 401, "not working", structured-output failure, or any symptom of things misbehaving), don't jump to causes and solutions from the symptom alone. Multiple providers and models can produce the same symptom for different reasons.

**Required before suggesting fixes (the two-question gate):**

1. **Which provider and which model?** If the user hasn't said, ask in one line. Do NOT skip this gate by inferring providers from `/run_configs` — `/run_configs` tells you what is *configured*, not what the user is currently using. Without the user's answer, any subsequent `available_models` check or latency diagnosis is fighting the wrong case.
2. **What's the exact error?** Status code, message, or screenshot text. "Not working" could be auth, quota, model activation, or payload shape.

Only after both are answered, check connected providers via `available_models`:

Read `references/knowledge/api_docs/get_api_available_models.md`, then:
`call_kiln_api("GET", "/api/available_models", jq_filter="[.[] | .provider_id] | unique")`

Then propose causes — **as hypotheses, not conclusions.** *"Likely cause — OpenRouter latency; secondary possibility — json_schema enforcement. We can rule in/out by…"* If the root cause isn't clear from the info gathered, admit uncertainty — don't manufacture a three-cause story to sound authoritative.

### Approach for first-time setup (no error symptom)

These two paths are for setting up a provider from scratch, not for diagnosing errors. If the user reported an error, go back to **Diagnose First** above.

#### Pre-Connect Check (do this before asking)

Before asking the user whether a provider is connected, check yourself. The agent has the tool — the user shouldn't have to answer questions the API can answer.

Read `references/knowledge/api_docs/get_api_available_models.md`, then:
`call_kiln_api("GET", "/api/available_models", jq_filter="[.[] | .provider_id] | unique")`

- If the target provider appears → skip setup and move to model selection / adding a specific model.
- If the provider is missing → proceed to **Connect the Provider**.

Do **not** ask the user "are you connected to X?" as an opening move — that's a verification the agent can do.

#### Triage: Existing Project or New?

Before diving in, determine context:

**Existing Project:** The user already has a project and task. Check existing run configs for connected providers:

Read `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_run_configs.md`, then:
`call_kiln_api("GET", "/api/projects/{project_id}/tasks/{task_id}/run_configs", jq_filter="[.[] | {name, provider: .run_config_properties.model_provider_name, model: .run_config_properties.model_name}]")`

If configs exist with providers → they already have at least one provider connected. The issue is likely a missing *additional* provider, an expired key, or a billing problem.

If no configs exist → they may have just created the task and need to connect their first provider.

**New Project (No Task Yet):** The user is brand new to Kiln and needs to connect at least one provider. Ask: "Which AI services does your team use? For example — OpenAI (ChatGPT), Google (Gemini), Anthropic (Claude)? Or do you have an OpenRouter account?"

### Explain Providers (If User Is Non-Technical)

Only use this explanation when the user seems confused. If they're technical and just need a link, skip to connecting.

> **Providers** are the companies that run AI models — like OpenAI (makes ChatGPT/GPT), Google (makes Gemini), and Anthropic (makes Claude). To use their models in Kiln, you need an **API key** — think of it as a password that lets Kiln talk to that company's AI on your behalf.
>
> Your team might already have API keys set up for other projects. Check with whoever manages your AI or cloud services — they'll know if you have an account with any of these providers.

### Connect the Provider

Deep-link the user to the provider setup page:

> "Let's get you connected. Head to the provider setup page — you'll enter your API key there:
>
> [Add Provider](http://localhost:8757/settings/providers)
>
> If you already have a key, paste it in and you're good to go. If you're not sure where to get one, I can help with that too."

Deep-link to [Add Provider](http://localhost:8757/settings/providers) when the user needs to connect a provider. Use [Add Custom Model](http://localhost:8757/settings/providers/add_models) only when the user is adding an OpenAI-compatible custom model.

### Verify

After the user says they've added a key, verify it works:

Read `references/knowledge/api_docs/get_api_available_models.md`, then:
`call_kiln_api("GET", "/api/available_models", jq_filter="[.[] | .provider_id] | unique")`

If their provider shows up → success, continue to model/config selection. If not → the key may be wrong, expired, or have billing issues (see Troubleshooting).

### Custom Models (OpenAI-compatible)

When the user wants to add a custom or OpenAI-compatible model, offer **both** paths and let them pick:

- **API (fast):** `POST /api/provider/openai_compatible` — agent fills in the model_id, base_url, and api_key.
- **UI (more control):** [Add Custom Model](http://localhost:8757/settings/providers/add_models) — form with advanced settings, visual defaults, and a test-connection button.

Default to offering both. Only pick the API path unilaterally if the user has explicitly said "just do it" or the context makes manual UI entry impractical.

### IT Handoff (If Needed)

When the user needs to ask their IT team for help, give them this checklist to forward:

> **What we need:** An API key for [provider name] so we can use their AI models through Kiln.
>
> **Specifically:**
> 1. An API key with permission to call chat/completions endpoints
> 2. Billing enabled on the account (most providers require a payment method even for free-tier usage)
> 3. The key should have access to the models we want to use (some providers require per-model activation)
>
> **Where to get it:**
> - OpenAI: https://platform.openai.com/api-keys
> - Google Gemini: https://aistudio.google.com/apikey
> - Anthropic: https://console.anthropic.com/settings/keys
> - OpenRouter: https://openrouter.ai/keys

Adapt the checklist to the specific provider they need.

## Provider Reference (quick lookup)

| Provider | Where to get a key | Kiln UI entry |
|----------|--------------------|---------------|
| OpenAI | https://platform.openai.com/api-keys | [Add Provider](http://localhost:8757/settings/providers) |
| Google Gemini | https://aistudio.google.com/apikey | [Add Provider](http://localhost:8757/settings/providers) |
| Anthropic | https://console.anthropic.com/settings/keys | [Add Provider](http://localhost:8757/settings/providers) |
| OpenRouter | https://openrouter.ai/keys | [Add Provider](http://localhost:8757/settings/providers) |
| OpenAI-compatible (custom) | provider-specific | [Add Custom Model](http://localhost:8757/settings/providers/add_models) |
| Ollama (local) | no key — just a local URL | [Add Provider](http://localhost:8757/settings/providers) |

Point the user to their provider's row. Do not guess which provider a mystery key belongs to — ask.

## Troubleshooting

| Symptom | Likely Cause | Action |
|---------|-------------|--------|
| "I entered my key but models aren't showing up" | Key is invalid, expired, or has no billing | Ask user to verify the key works in the provider's own dashboard. Check for billing/quota issues. |
| "It says unauthorized / 401" | Wrong key or key doesn't have the right permissions | Re-enter the key. Check that it's an API key (not a login password or session token). |
| "I can see some models but not the one I want" | Provider requires per-model activation (common with Bedrock, Vertex) | Check provider's model access settings. Some models need explicit opt-in. |
| "My IT team gave me a key but I don't know which provider it's for" | Key format can hint: `sk-...` = OpenAI, `AIza...` = Google | Ask user to check with IT which service the key is for. |
| "Everything was working and now it's broken" | Billing limit hit, key revoked, or provider outage | Check provider status page. Ask user to verify billing is current. |
