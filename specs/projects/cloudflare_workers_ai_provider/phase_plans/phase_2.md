---
status: complete
---

# Phase 2: Connect-Screen UI

## Overview

Phase 1 added the backend (`connect_cloudflare`, disconnect, config keys) and the web plumbing (schema, name map, logo). This phase adds the Cloudflare card to the connect-provider screen so users can actually connect. The card is a data entry in the existing `providers` list, rendered by the existing provider row and connect dialog; no new markup or controls.

## Steps

1. `app/web_ui/src/routes/(fullscreen)/setup/(setup)/connect_providers/connect_providers.svelte`:
   - Add a provider entry after Featherless AI, with every string exactly as in `ui_design.md`:

     ```ts
     {
       name: "Cloudflare",
       id: "cloudflare",
       description: "Open models on the edge, plus an AI gateway.",
       featured: false,
       api_key_steps: [
         "Go to https://dash.cloudflare.com/?to=/:account/ai/workers-ai and click 'Use REST API'",
         "Click 'Create a Workers AI API Token', create the token, then copy it and paste it below",
         "On the same page, copy your Account ID and paste it below",
         "Optional: to send requests through Cloudflare AI Gateway (a router to other AI hosts), enter a gateway ID. Enter 'default' to have Cloudflare create one.",
         "Click 'Connect'",
       ],
       api_key_warning: "Some models require Cloudflare's Workers Paid plan.",
       api_key_fields: ["API Token", "Account ID", "AI Gateway ID - Optional"],
       optional_fields: ["AI Gateway ID - Optional"],
     }
     ```

   - Add `cloudflare` to the `status` map (after `featherless_ai`), same shape as the others.
   - In `check_existing_providers`: `if (data["cloudflare_api_key"] && data["cloudflare_account_id"]) status.cloudflare.connected = true`.

## Tests

In `connect_providers.test.ts`:

- `renders the Cloudflare card with its description and logo`: the row shows the Cloudflare image and the approved description.
- `shows the three Cloudflare fields and the Workers Paid warning`: opening the dialog shows the `API Token`, `Account ID` and `AI Gateway ID - Optional` inputs, the approved warning and the five steps, with the dashboard URL rendered as a link.
- `submits Cloudflare without the optional gateway field`: with token and account filled and gateway empty, the POST body is `{provider: "cloudflare", key_data: {"API Token", "Account ID"}}` with no gateway key.
- `submits the gateway ID when entered`: the POST body includes `"AI Gateway ID - Optional"`.
- `does not submit Cloudflare when the account ID is missing`: no connect request is made, and the fields are flagged.
- `shows Cloudflare as connected when the token and account ID are saved`.
- `does not show Cloudflare as connected when only one of the token or account ID is saved` (parametrized over both).
