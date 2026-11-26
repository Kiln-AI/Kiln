---
status: complete
---

# Remove GEPA / Prompt Optimization

Remove the GEPA-based automatic prompt optimization feature ("Kiln Prompt Optimizer") from Kiln and kiln_server. [Harness Tuner](https://github.com/Kiln-AI/harness-tuner) replaces it: it tunes the whole agent harness (tools, prompts, skills, model and settings), not just the prompt.

This project spans two repos:

- **Kiln** (desktop app, core lib, web UI): remove the prompt optimization job API, the `PromptOptimizationJob` data model, the generated kiln_server client code for it, the `/prompt_optimization` UI and every entry point to it, the agent policy annotations, and its tests.
- **kiln_server**: remove the `prompt_optimization` package (GEPA, DSPy), the jobs route, the `gepa-job` job type and Cloud Run config, the related dependencies, Docker and config entries, and the GEPA and prompt optimization docs in the copilot chat (`kiln-chat`) skill.

## Decisions

- **Older clients get a clear sunset error.** Older desktop builds still show the feature. When one of them calls a prompt optimization endpoint on kiln_server, the server responds with an error saying the feature has been sunset and pointing to Harness Tuner. It must not return a generic 404 or 422.
- **Existing user data keeps working.** Prompts created by the optimizer (`generator_id="kiln_prompt_optimizer"`) still load and still show as "Kiln Optimized". Existing `prompt_optimization_jobs/` folders on disk are simply ignored, and we don't delete them.
- **The billing machinery stays.** The Kinde entitlement and usage plumbing (`check_entitlements`, `org_has_entitlement`, `record_usage_for_org`) stays because it's generic. Only the logic specific to prompt optimization goes, such as `checkPromptOptimizationAccess` and the `prompt-optimization` feature code usage.
- **Copilot docs are cleaned.** The docs only about GEPA and prompt optimization in the `kiln-chat` skill are deleted. Other docs that mention the feature are edited so the copilot no longer recommends it.
- **Out of scope:** the Optimize hub (`/optimize`) and the evals train split stay. Only wording that refers to "automatic optimizers" is updated.
