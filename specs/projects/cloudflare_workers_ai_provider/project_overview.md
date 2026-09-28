---
status: draft
---

# Cloudflare Workers AI Provider

Add Cloudflare Workers AI as a Kiln provider.

We want a pretty standard AI provider. Ideally no UX beyond what every provider already has.

## Questions to Research

- Do we add Cloudflare AI Gateway as well? One API or two?
- Does Cloudflare publish a JSON model list we can use from our skill that adds new models (`claude-maintain-models`)? We should update that skill's docs with how to keep the Cloudflare model list up to date.
- What's their "model list" concept: one static list (like OpenRouter, Anthropic), or a dynamic "models your account can access" list?
