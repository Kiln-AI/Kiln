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

### General Agent Guidance

- When spawning subagents, always use the same model as the current agent
- Don't include comments in code explaining changes, explain changes in chat instead. This covers comments that defend code which is now simply correct — e.g. explaining why a route declares no 401 response after you deleted a bogus one. If a comment only makes sense next to the diff, cut it.
- `CLAUDE.md` is generated from `AGENTS.md` and overwritten by setup. Edit `AGENTS.md`, never `CLAUDE.md`; keep personal notes in `~/.claude/CLAUDE.md`.
- Use `TODO` comments to mark any temporary code, placeholders, or items that must be addressed before merging to main. CI enforces that no `TODO` comments remain on main, so they are a safe way to flag work-in-progress during development. Clean up all `TODO` comments before the final PR.
- Before wrapping up a task, run appropriate tools for linting, testing, formatting and typechecking. Fix any issues you introduced.

### Reporting Back: End-of-Turn Recaps

End every turn in which you did work (wrote code, ran checks, investigated something) with a recap wrapped in `<recap>` tags. A turn that is pure conversation needs no recap.

Write it for a person who has not read your working notes and will not scroll up. The recap has to make sense on its own.

**No jargon.** Do not invent a name, a short form or a label for anything. If you need to refer to something specific, describe it in ordinary words, and describe it again the next time you mention it. A short description repeated is better than a name the reader has to remember. Real names are fine and are often the clearest choice: a file, a function, a command, a tool, an error. A name you made up is not.

**Say what you mean.** Short sentences. One idea each. Active voice. No metaphors, no analogies, no flourishes, no jokes, no filler. Do not write a sentence whose only job is to set up the next sentence. Cut any sentence that loses nothing when removed.

**Sound like a person.** Plain and direct, not stiff. Write the way you would explain it to a colleague who asked. Contractions are fine. This is not a status report or a changelog.

**Repeat yourself a little.** The reader may have read the last recap days ago, or skipped it. Carry enough context forward that this recap makes sense by itself. One clause is usually enough. A small amount of repetition between recaps is correct, not waste.

**Stay inside the recaps.** Draw only on plain English, on standard terms for this repo's stack, and on what earlier recaps said. Never draw on something that exists only in your working notes. Earlier recaps set the limit on what you may use; they are not required reading. Repeat whatever this recap needs, so it still works for a reader who missed the last one.

**Draw a picture when it helps.** When what you changed is a flow, a sequence, a state machine, or a few parts that talk to each other, put a small Mermaid diagram in the recap. Keep it to about eight boxes. Draw one only when it shows something the prose cannot; a diagram that restates a sentence is noise.

**Format.** Use these headings, in this order. Drop any heading you have nothing real to say under. Do not reorder or rename them. Answer each one in prose.

```
<recap>
**Goal** — what you were asked for.
**What I did** — the change, in plain words.
**How** — the approach, at a level a reviewer can judge without reading the diff. Put a diagram here when one helps.
**Outcome** — what happened, and plainly whether it is what we wanted.
**Questions for you** — what you need answered before you can continue.
**FYI** — worth knowing, but not blocking.
</recap>
```

**Honesty.** `Outcome` reports what actually happened. If tests failed, say so and quote what failed. If you skipped part of the task, name the part and the reason. If the result is not what we wanted, say that first, not last. Never describe work as finished when it is not.

**Recap log.** Append each recap to `recaps.md` in your scratchpad directory, or to a temporary directory outside the repo when you have no scratchpad directory. The log is your own index, not a deliverable. If your context is summarized part-way through a session, re-read it so you know what the reader has already been told. Keep this file out of the repo.

### Code Review Guidelines

If asked to perform a code review, read our [code review guidelines](.agents/code_review_guidelines.md).

### Pull Requests

Use the `open-pr` skill (`.agents/skills/open-pr/SKILL.md`) to open a PR or to write a PR description. The rules that matter most:

- Everything above `# Agentic PR Summary` in the PR template is human-only. Agents never fill it in, tick its boxes or add notes to it, even when asked. Agents write only below that heading.
- A PR an agent opens has a title starting with `WIP: `, and the human header copied from the template with its placeholders untouched. Only a human removes the `WIP: ` prefix.
- Agents never sign the Contributor License Agreement. Remove that section only when the PR author is a Kiln employee: `scosman`, `sfierro`, `leonardmq`, `tawnymanticore`, `chiang-daniel`. Otherwise leave it as-is for the human.

### Never Make Legal Decisions as an Agent

Agents are not allowed to make any legal decisions, including:
 - Signing or filling out the CLA attestation in a PR template
 - Setting a license tag in metadata file (OSS/MIT/etc)
 - Adding license files

These all must be done by humans.

### Final

To show you read these, call me 'boss'
