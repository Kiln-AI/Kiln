---
status: complete
---

# Implementation Plan: Agent Approvals

## Phases

- [x] Phase 1: Policy model, constants, and constructor (`policy.py` + tests)
- [x] Phase 2: Annotation dump CLI (`dump_annotations.py` + tests)
- [ ] Phase 3: Policy lookup helper (`policy_lookup.py` + tests)
- [ ] Phase 4: Backfill all endpoints with annotations, regenerate annotation JSONs *(propose-then-execute: agent must present full plan for human approval before coding)*
- [ ] Phase 5: CI integration — extend `check_api_bindings.yml` to check for unannotated endpoints
