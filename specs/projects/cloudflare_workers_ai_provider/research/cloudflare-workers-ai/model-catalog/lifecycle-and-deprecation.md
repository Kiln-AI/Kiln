# Model Lifecycle and Deprecation on Workers AI

## How often models change

Cloudflare adds text-generation models often and retires old ones in batches.

**Additions in 2026** (from the [Workers AI changelog directory](https://github.com/cloudflare/cloudflare-docs/tree/production/src/content/changelog/workers-ai) and model `created_at` dates): GLM-4.7-Flash (Feb 13), Nemotron 3 Super (Mar 11), Kimi K2.5 (Mar 19), Gemma 4 26B A4B (Apr 4), Kimi K2.6 (Apr 20), Kimi K2.7 Code (Jun 12), GLM-5.2 (Jun 16), DeepSeek V4 Flash + Pro (Aug 14), Qwen 3.8 27B (Aug 17), GLM-5.3 Flash (Aug 26), GLM-5.3 (Aug 28). About one new notable text model per month, sometimes several in two weeks.

**Retirement batches found:**

| Announced | Retired | Notice | Models | Source |
|---|---|---|---|---|
| 2024-06-11 | 2024-06-30 | 19 days | `@cf/meta/llama-2-7b-chat-int8` | [Workers AI changelog](https://developers.cloudflare.com/workers-ai/changelog/) (via search snippet) |
| 2025-09-18 | 2025-10-01 | 13 days | 19 models: `@hf/thebloke/*-awq` (zephyr, mistral-7b-v0.1, llama-2-13b, openhermes-2.5, neural-chat, llamaguard-7b, deepseek-coder base/instruct), `@cf/deepseek-ai/deepseek-math-7b-instruct`, `openchat-3.5-0106`, `falcon-7b-instruct`, `discolm-german-7b`, `qwen1.5-*` (4), `tinyllama-1.1b`, `@hf/nexusflow/starling-lm-7b-beta`, `una-cybertron-7b` | [`release-notes/workers-ai.yaml`](https://github.com/cloudflare/cloudflare-docs/blob/production/src/content/release-notes/workers-ai.yaml) |
| 2026-05-08 | 2026-05-30 | 22 days (Kimi K2.5 was first announced for May 10, then extended) | 18 models incl. `@cf/moonshotai/kimi-k2.5`, `@cf/meta/llama-3.1-8b-instruct`, `@cf/meta/llama-3.1-70b-instruct`, `@cf/meta/llama-3-8b-instruct(-awq)`, `@cf/google/gemma-3-12b-it`, `@cf/mistral/mistral-7b-instruct-v0.1`, all remaining `@hf/*`, `phi-2`, `sqlcoder-7b-2`, `bart-large-cnn`, `uform-gen2-qwen-500m` | [2026-05-08 changelog](https://developers.cloudflare.com/changelog/post/2026-05-08-planned-model-deprecations/) |

Takeaway: notice periods are short (2–3 weeks). Kiln's remote model list can react in that time, but only if someone is watching.

## What retirement looks like

1. **Announcement** as a changelog post and release-notes entry on developers.cloudflare.com. The May 2026 post has "Recommended replacements" and a flat list of IDs. It also warns: "LoRA models may be deprecated in the future."
2. **Metadata**: Cloudflare adds a `planned_deprecation_date` property to each affected model (e.g. `{"property_id": "planned_deprecation_date", "value": "2026-05-30"}`) ([docs commit 225279a14](https://github.com/cloudflare/cloudflare-docs/commit/225279a1461d1a39c752889304c65380688e1991)). The docs show a "Planned deprecation" pill.
3. **After the date**: the model disappears from the default `/ai/models/search` response. The API keeps it visible with `include_deprecated=true` "for up to three months after their deprecation date" ([OpenAPI](https://github.com/cloudflare/api-schemas)). The docs sync drops it.
4. **Calls to a retired ID** most likely return `400` / error `5007` "No such model `${model}` or task" ([errors.mdx](https://github.com/cloudflare/cloudflare-docs/blob/production/src/content/docs/workers-ai/platform/errors.mdx)). *I did not verify this with a live call to a retired model.*
5. **Exception: silent aliasing.** "Requests will be automatically aliased to Kimi K2.6 on May 30, 2026, which has a higher price." So a retired ID can keep working while it actually runs a different, more expensive model. A Kiln entry for such an ID would give no error and wrong results/cost. This is the strongest reason to remove retired IDs promptly.

## Other lifecycle states

- **Plan changes.** On 2026-07-28 Kimi K2.6, Kimi K2.7 Code and GLM-5.2 moved to Workers Paid only; Free-plan calls now get `403` / `5035` ([changelog](https://developers.cloudflare.com/changelog/post/2026-07-28-models-require-workers-paid/)). New big models (DeepSeek V4, GLM-5.3) launched as paid-only: "requires the Workers Paid plan or prepaid AI Gateway credits". Tracked by the `require_workers_paid` property.
- **Preview → dated release.** DeepSeek V4 Flash "supersedes the preview version" ([changelog](https://developers.cloudflare.com/changelog/post/2026-08-14-deepseek-v4-workers-ai/)), and the released IDs carry date suffixes (`-0731`, `-0813`). Expect future snapshot IDs to follow this pattern and older snapshots to be retired.
- **Experimental / beta.** `hide_experimental` search filter; `beta` property.
- **Metadata edits after launch.** Context windows and reasoning controls are corrected after launch (DeepSeek V4 Flash context fixed 2026-09-17; reasoning efforts reworked 2026-09-24). Kiln's entries should be re-checked, not just added once.

## Where to watch

| Signal | How to read it | Notes |
|---|---|---|
| `planned_deprecation_date` in model data | `curl -s https://ai-cloudflare-com.pages.dev/api/models \| jq '.models[] \| select(any(.properties[]; .property_id=="planned_deprecation_date")) \| {name, date: (.properties[] \| select(.property_id=="planned_deprecation_date").value)}'` | Unauthenticated. Best machine signal. Undocumented endpoint. |
| Default search vs `include_deprecated=true` | Diff the two `/ai/models/search` results | Needs a Cloudflare token. |
| Model missing from current list | Compare Kiln's `@cf/` IDs to the current list | Works with any list source. |
| Changelog | `https://developers.cloudflare.com/changelog/product/workers-ai/`; RSS route exists at `/changelog/rss/[product].xml` (so likely `.../changelog/rss/workers-ai.xml`, not fetched) | Human-readable; has replacement advice and alias notes. |
| Docs repo | `git log -- src/content/workers-ai-models src/content/changelog/workers-ai` in `cloudflare/cloudflare-docs` | Commit titles like "Announce planned model deprecations". |
