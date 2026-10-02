---
status: complete
---

# Code Conventions Skills

Add skills for coding conventions and gotchas to both the Kiln repo and kiln_server, so agents (and humans) writing or reviewing code follow the same rules:

- avoid redundant comments
- no zigzag comments that explain something's undoing when it is redundant
- try to modularize things
- avoid globals
- try to have one entry point in the runtimes, and not modules self-initializing
- proper modules
- watch out for things like settings.yaml that lazy loads

We started with an audit of red flags in both repos ([research/audit](research/audit/README.md)), and derive the general rules and the refactoring needs from it.

## Decisions so far

- Scope of this project: the two skills, cheap mechanical checks to back them, and a sweep of the bad comments found in the audit. Refactors become their own spec projects later. The small bugs found in the audit are fixed separately, one PR each.
- Existing code is grandfathered: rules apply to new and changed code. Refactors fix the old code over time.
- Each repo keeps its own copy of the universal rules, and kiln_server's started from Kiln's. kiln_server adds its own repo-specific gotchas.
- Web UI conventions go wherever fits best (together with `kiln-ui` or separate).
- Mechanical checks are in, as long as they're cheap.
- kiln_ai `Config` precedence stays as it is (settings.yaml wins over env vars). We document it as a gotcha and don't change the behaviour now.
