---
status: complete
---

# Implementation Plan: Remove GEPA / Prompt Optimization

Three PRs (kiln_server, Kiln, docs), plus a manual infra step. Section numbers refer to [architecture.md](architecture.md).

## Phases

- [ ] Phase 1: kiln_server, sunset and removal. Covers the sunset router and its tests (§1.1, §1.4), deleting the package, routes, job util, job type and Cloud Run yml (§1.2), the packaging and config edits with `uv lock`, `FeatureCode`, and the runner and Kinde test updates (§1.3, first part). The kiln_server checks pass.
- [ ] Phase 2: kiln_server docs and content. Covers the copilot chat `kiln-chat` skill deletions and edits, and the conventions skill docs (§1.3, docs part). Run the final check (§1.5) and the old-client acceptance test (§4). Open the kiln_server PR.
- [ ] Phase 3: Kiln backend. Covers the datamodel, studio API and agent overview, eval_api wording, annotations, the OpenAPI tag, the regenerated client, and the multipart test (§3.1 Python files, §3.2-3.5). Regenerate the client from the Phase 1 branch.
- [ ] Phase 4: Kiln web UI. Covers the routes, prompts page, generator picker, entitlement helper, types, the regenerated `api_schema.d.ts`, deleting the duplicate schema, e2e, and the README (§3.1 UI files, §3.6). Run the final check (§3.7). Open the Kiln PR.
- [ ] Phase 5: Docs repo. Add the deprecation notice and mark listings (§5). Open the docs PR.
- [ ] Phase 6: Infra cleanup, run after the kiln_server prod deploy. Covers the Cloud Run job and the GCS `gepa-job` data in staging and prod (§2). Needs your explicit go-ahead before anything is deleted.
