---
status: complete
---

# UI Design: Cloudflare Provider

The UI is the standard provider entry on the connect-provider screen (`connect_providers.svelte`), with the same layout and behavior as other providers that have more than one field (Fireworks, W&B). No new screens or controls. This doc records the approved user-facing strings.

## Logo

`assets/cloudflare.svg` in this spec folder. It ships as `app/web_ui/static/images/cloudflare.svg` and is registered in `provider_image.ts`.

## Provider Card

- **Name:** `Cloudflare`
- **Description:** `Open models like GLM, Kimi and DeepSeek, on Cloudflare.`

## Connect Steps

1. `Go to https://dash.cloudflare.com/?to=/:account/ai/workers-ai and click 'Use REST API'`
2. `Click 'Create a Workers AI API Token', create the token, then copy it and paste it below`
3. `On the same page, copy your Account ID and paste it below`
4. `Optional: to send requests through Cloudflare AI Gateway (a router to other AI hosts), enter a gateway ID. Enter 'default' to have Cloudflare create one. Your token needs AI Gateway permissions.`
5. `Click 'Connect'`

## Field Labels

- `API Token`
- `Account ID`
- `AI Gateway ID - Optional` (listed in `optional_fields`, like W&B's optional fields)

## Warning

`Some models require Cloudflare's Workers Paid plan.`

## Connect Errors

| Case | Message |
|---|---|
| Bad account ID | `Failed to connect to Cloudflare. Invalid Account ID.` |
| Bad token, or token without access to this account | `Failed to connect to Cloudflare. Invalid API Token, or the token doesn't have Workers AI access for this Account ID.` |
| Bad gateway ID, or token without gateway access | `Failed to connect to Cloudflare. AI Gateway '<id>' not found, or your token doesn't have AI Gateway access. Fix permissions, or remove the gateway ID.` |
| Anything else | `Failed to connect to Cloudflare. Error: [<status>] <response text>` |

If live testing shows Cloudflare can't tell two of these cases apart, the architecture merges the affected rows and keeps the wording as close to these as possible.

## Runtime Model-Mismatch Error

Only used if the optional runtime no-substitution check is built (see the functional spec).

`Cloudflare ran a different model (<actual>) than the one requested (<requested>). Kiln stopped the request so results aren't from the wrong model.`

## Other Surfaces

- The model picker shows the provider as `Cloudflare`, via the provider name map in `stores.ts`.
- Model-call errors show Cloudflare's own message, as for other providers. Rate-limit errors go through Kiln's standard rate-limit handling (see the functional spec's Rate Limits section).
