## Project Overview

Kiln is an app for building AI systems. It includes evals, synthetic data gen, fine tuning, RAG, and more. It has an intuitive UI as well as a python library.

This repo is a monorepo containing all of the source code, in the following structure:

- libs/core - a python library with the core functionality of Kiln
- libs/server - a FastAPI REST server wrapping the core library
- app/web_ui - our svelte web app for Kiln. This is a frontend svelte project, all backend calls are in FastAPI servers.
- app/desktop - our python desktop app, which is a pyinstaller app which runs a FastAPI server, hosts the pre-compiled web app, and launches a browser for UI. Compiles to all major platforms. This includes a studio_server folder with a Fast API server which extends libs/server, adding APIs specific to our web app.

### Project Goals

- Very high code quality
- Strongly typed
- Well tested
- Very intuitive UI. Accessible to the inexperienced, but powerful for the experienced.
- Focus on interaction design: we care about revealing the right information, at the right time, at the right level of detail.
- Focus on visual design: we want a modern, functional, attractive UI. Think Apple not Google.

### Tech Stack

- Backend: python (3.10+ for library, 3.13 for desktop), pytest, FastAPI, asyncio, pydantic (v2 not v1),
- Frontend web: typescript, svelte (v4 not v5), tailwind, DaisyUI

### Agent Tools

Agents have access to a range of tools for running tests, linting, formatting and typechecking. Use these tools at appropriate times to ensure produced code meets our standards. All checks must pass before merging. When iterating on a specific failure, use the targeted command before re-running the full suite.

- **All checks:** `uv run ./checks.sh --agent-mode` (agent mode suppresses output unless there's a failure)

| Check | Fix | Description |
|---|---|---|
| `uv run ruff check` | `uv run ruff check --fix` | Python lint |
| `uv run ruff format --check .` | `uv run ruff format .` | Python format |
| `uv run ty check` | — | Python type check |
| `uv run python3 -m pytest --benchmark-quiet -q -n auto .` | — | Python tests |
| `npm run lint` | — | Web lint (from `app/web_ui`) |
| `npm run format_check` | `npm run format` | Web format (from `app/web_ui`) |
| `npm run check` | — | Web type check and svelte check (from `app/web_ui`) |
| `npm run test_run` | — | Web tests (from `app/web_ui`) |
| `npm run build` | — | Web build (from `app/web_ui`) |
| `app/web_ui/src/lib/check_schema.sh` | `app/web_ui/src/lib/generate_schema.sh` | OpenAPI client up to date |
| `misspell` | — | Spelling check (optional if not installed) |

Our end-to-end UI tests are separate and not part of `checks.sh`.

### Agent Prompts

Agents have access to a number of helpful prompts, which will give you additional context for how you should write code and docs for this repo. Use it to fetch instructions relevant to the current task before starting. For example, read `python_test_guide.md` before writing tests, and invoke the `kiln-ui` skill (`.agents/skills/kiln-ui/SKILL.md`) before any change under `app/web_ui`; it loads `frontend_design_guide.md` and `frontend_controls.md` and adds a component plan and a gate.

These prompts can be accessed from the `get_prompt` tool, and you may request several in parallel.

Before writing or changing code, invoke the `kiln-conventions` skill (`.agents/skills/kiln-conventions/SKILL.md`). It holds the code rules, the gotchas for each area, and a gate to run on your change.

### General Agent Guidance

- When spawning subagents, always use the same model as the current agent
- `CLAUDE.md` is generated from `AGENTS.md` and overwritten by setup. Edit `AGENTS.md`, never `CLAUDE.md`; keep personal notes in `~/.claude/CLAUDE.md`.
- Use `TODO` comments to mark any temporary code, placeholders, or items that must be addressed before merging to main. CI enforces that no `TODO` comments remain on main, so they are a safe way to flag work-in-progress during development. Clean up all `TODO` comments before the final PR.
- Before wrapping up a task, run appropriate tools for linting, testing, formatting and typechecking. Fix any issues you introduced.

### Code Comments

Comments follow §A of `.agents/skills/kiln-conventions/references/rules.md`: write them for someone opening the file cold, never narrate the change, never restate the code. Review-bot findings about comments, including nitpicks, are required fixes.

### Code Review Guidelines

If code reviewing, always read [`.agents/code_review_guidelines.md`](.agents/code_review_guidelines.md) before starting your review.

### Pull Requests

Use the `open-pr` skill (`.agents/skills/open-pr/SKILL.md`) to open a PR or to write a PR description.

Before you open a PR, and before each `git push` to a branch with an open PR, run the `docs-sync` skill (`.agents/skills/docs-sync/SKILL.md`) to update the docs and skills that the change makes stale.

If you get a user message like the one below, read `.agents/skills/open-pr/references/repair_pr.md` and follow its instructions.

> A pull request was just created for this branch from the Claude Code UI: https://github.com/Kiln-AI/Kiln/pull/NNNN
> You don't need to create one. Reference this PR going forward — pushing more commits to this branch will update it.

### Never Make Legal Decisions as an Agent

Agents are not allowed to make any legal decisions, including:
 - Signing or filling out the CLA attestation in a PR template
 - Setting a license tag in metadata file (OSS/MIT/etc)
 - Adding license files

These all must be done by humans.

### Final

To show you read these, call me 'boss'
