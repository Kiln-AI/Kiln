---
status: draft
---

# Cloud Sandbox Developer Experience

A meta project to improve the ability to work on the Kiln repo inside Claude Code
cloud sandboxes.

I use Claude Code's cloud sandboxes more and more, so I really value efficiency in
that environment. I've seen a bunch of issues — the list below is not complete.
The goal is to make the best fixes for working in cloud sandboxes: process
improvements, `CLAUDE.md`/`AGENTS.md` updates, setup script improvements, etc.

Issues seen so far:

- Can setup be faster? A `uv sync` cache? On another project I added an R2 cache
  for cargo. How fast is setup today? Is it worth optimizing? Are other startup
  steps costing us?
- Some code uses tkinter, which doesn't work on headless Linux. It isn't really
  needed often — we can host a web server, we can run things.
- Can't run the script to update the OpenAPI schema (tkinter issue).
- Test performance: is it fast enough? Should we add something to speed it up?
  Are we getting parallel performance?
- There may be many more.

A report from another agent that encountered and worked around some of these
issues is attached as a starting point. Its solutions may be far from optimal —
it is a starting point, not a plan.

Planning must begin with a research phase: run experiments, clear the cache and
re-run the startup script, measure times, try running things. Get data before
planning.

## Research

The research phase is complete. See [research_findings.md](research_findings.md)
for measurements taken on a live sandbox.
