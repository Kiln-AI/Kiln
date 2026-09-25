---
status: complete
---

# Phase 5: Web UI and docs

## Overview

Make TypeSafe AI a provider a user can see and connect to, and bring the repo's
generated and agent-facing artifacts back in step with the enum member Phase 1 added.

The backend is already complete: `connect_typesafe`, the connect/disconnect dispatch,
`provider_name_from_id`, and `provider_warnings` all landed in Phase 1. What is missing
is everything above the API line — the connect page card, the two TypeScript provider
maps, the icon, and the regenerated OpenAPI client — plus the agent tooling and skill
docs that enumerate providers.

The schema regeneration and the TypeScript map entries are one indivisible change.
`provider_name_map` and `provider_image_map` are `Record<ModelProviderName, …>`, so the
moment the regenerated `api_schema.d.ts` teaches `ModelProviderName` about `typesafe`,
both maps become non-exhaustive and `npm run check` fails. This phase is the first where
`checks.sh` must come back fully green, schema check included.

No new UI markup. The connect page renders its cards from a `providers` array; a new
provider is a data entry in that array plus a `status` key, both rendered by markup that
already exists. That is what the component plan below records.

## Component plan

| Element | House control used | Sibling screen it matches | Justification if custom |
|---|---|---|---|
| TypeSafe AI provider row (icon, name, description, Connect button) | Existing `{#each providers}` card markup in `connect_providers.svelte`; new entry is data only | The Featherless AI and Cerebras rows on the same screen | |
| "Connect TypeSafe AI" API key dialog (steps list, one API Key field, Connect button) | Existing `api_key_provider` dialog markup, driven by `api_key_steps` / `api_key_fields` | The Featherless AI dialog on the same screen | |
| Connected state (check icon, hover Disconnect) | Existing `is_connected` branch, driven by `status.typesafe.connected` | Every connected provider row on the same screen | |

Sibling screen: the connect providers page itself, Featherless AI row. Vertical rhythm is
unchanged — the `{#each}` container owns the `gap-y-6` between rows and nothing in this
change touches it.

Gate justification, `SHARED_CONTROL_TOUCHED` at `app/web_ui/src/lib/ui/provider_image.ts:27`:
the edit adds one key to the `provider_image_map` data table. No markup, props or
rendering behaviour in `get_provider_image` changes, and no existing key is touched, so
no call site can render differently. It cannot be split into its own commit either:
`provider_image_map` is typed `Record<ModelProviderName | "wandb" | "kiln_copilot", string>`
and `provider_name_map` in `stores.ts:560` is `Record<ModelProviderName, string>`, so both
stop compiling the moment `api_schema.d.ts` is regenerated in step 5. Regeneration and
both map entries are one indivisible change.

## Steps

1. `app/web_ui/static/images/typesafe.svg` — copy
   `specs/projects/jev_provider/assets/typesafe_jev_logo.svg` verbatim. Path data,
   `viewBox` and the delivered `fill` / `fill-opacity` stay exactly as supplied, matching
   `cerebras.svg` which also keeps a literal `fill="black"`.

2. `app/web_ui/src/lib/ui/provider_image.ts` — add `typesafe: "/images/typesafe.svg"` to
   `provider_image_map`, after the `featherless_ai` entry.

3. `app/web_ui/src/lib/stores.ts` — add `typesafe: "TypeSafe AI"` to `provider_name_map`,
   after the `featherless_ai` entry. The string must match `provider_name_from_id` in
   `provider_tools.py`.

4. `app/web_ui/src/routes/(fullscreen)/setup/(setup)/connect_providers/connect_providers.svelte`
   — three data additions, each placed after its `featherless_ai` neighbour:

   - a `providers` entry:

     ```ts
     {
       name: "TypeSafe AI",
       id: "typesafe",
       description: "Structured output only, with a probability for every answer.",
       featured: false,
       api_key_steps: [
         "Go to https://typesafe.ai",
         "Create a new API Key",
         "Copy the new API Key, paste it below and click 'Connect'",
       ],
       api_key_fields: ["API Key"],
     }
     ```

   - a `status.typesafe` block with the standard four fields
   - in `check_existing_providers`, `if (data["typesafe_api_key"]) { status.typesafe.connected = true }`

5. `app/web_ui/src/lib/api_schema.d.ts` — regenerate with
   `app/web_ui/src/lib/generate_schema.sh`. The only expected change is `| "typesafe"` on
   the `ModelProviderName` union.

6. `.agents/scripts/provider_utils.py` — add `"typesafe"` to `SKIP_PROVIDERS` with a
   comment saying the System One API has no OpenAI-compatible model listing the agent
   tooling can enumerate.

7. Skill docs, all three synced copies each (`.agents/skills/`, `.claude/skills/`,
   `.cursor/skills/`). Edit the `.agents` copy, then copy it over the other two so the
   three stay byte-identical:

   - `claude-maintain-models/SKILL.md` — a `typesafe` row in the provider `model_id`
     format table, and a short TypeSafe AI entry in the Provider Quirks Reference saying
     it is adapter-backed rather than LiteLLM-backed, structured output only, and that
     its models carry `adapter=ModelAdapterId.jev`.
   - `kiln-check-deprecation/SKILL.md` — a `typesafe` bullet under "Providers to skip",
     matching the `SKIP_PROVIDERS` change.

8. Run the full `uv run ./checks.sh --agent-mode` and the `kiln-ui` gate on the worktree.

## Tests

- `connect_providers.test.ts`: "shows TypeSafe AI as connected when a TypeSafe API key is
  already saved" — settings returns `{ typesafe_api_key: "..." }`, the TypeSafe AI row
  renders and shows the Connected state, which exercises the card entry, the `status`
  key, and the settings wiring together. A missing `status.typesafe` block would throw on
  render, and a missing settings line would leave the row showing Connect.
