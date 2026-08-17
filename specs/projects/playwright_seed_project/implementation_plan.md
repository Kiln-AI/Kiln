---
status: complete
---

# Implementation Plan: Playwright Seed Project

Phases 2 onward are fixture authoring, done through the UI. Each ends in `snapshot`
and a commit, so a lost session costs at most one phase. See
[architecture.md](architecture.md) for the group definitions and the authoring rules.

The OpenRouter key is needed from Phase 2 on. The implementing agent asks the user for
it; it is not recorded in any spec artifact.

## Phases

- [x] Phase 1: `playwright_server.sh` mechanics — home guard, seed, stamp, `reset`,
  `snapshot`, `ui_state` hint, load check. Capture the foundation fixture (project,
  structured task, plain task) through the UI. Document the commands in
  `USING_PLAYWRIGHT.md`. Run the full verification matrix.
- [x] Phase 2: Runs and ratings — 15–20 runs, spread ratings including unrated, a
  repair, two run configs. Then the saved prompt, dataset split, input transform, and
  feedback.
- [ ] Phase 3: Evals — one eval, judge config, results across both run configs. Carries
  specs with it.
- [ ] Phase 4: Skills and RAG — skills with `SKILL.md` bodies, then documents through
  RAG config. Prove the index rebuilds from a seeded sandbox. Final docs pass on what
  the fixture contains, and re-run matrix cases 1–4 against the finished fixture.
