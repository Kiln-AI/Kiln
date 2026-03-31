# `/spec setup` — Repo Setup

One-time (or incremental) setup for using the spec skill in a repo. Idempotent — won't clobber existing setup, only extends what's missing.

## Steps

### 1. Gitignore

Add `.specs_skill_state/` to `.gitignore`:

- If `.gitignore` exists: check if `.specs_skill_state/` is already present. If not, append it.
- If `.gitignore` doesn't exist: create it with `.specs_skill_state/` as the content.

This directory tracks per-user state (current project), so it should never be committed.

### 2. Directory Creation

Create `/specs/projects/` if it doesn't exist:

```bash
mkdir -p specs/projects
touch specs/projects/.gitkeep
```

The `.gitkeep` file ensures the empty directory is tracked by git.

### 3. Monorepo Detection

Scan for root markers in subdirectories to detect potential sub-projects. Common markers:

- `pyproject.toml`, `setup.py`, `setup.cfg` (Python)
- `package.json` (Node.js/TypeScript)
- `go.mod` (Go)
- `Cargo.toml` (Rust)
- `build.gradle`, `settings.gradle`, `pom.xml` (Java)
- `.csproj`, `.sln` (C#)
- `Gemfile` (Ruby)
- `composer.json` (PHP)
- `pubspec.yaml` (Dart)
- `DESCRIPTION`, `NAMESPACE` (R)

Ask the user:

> Is this a monorepo? I found these potential sub-projects:
> - [list paths with markers]
>
> Are there any other sub-projects I should know about?

**Always ask**, even if no markers are found (the user may have a non-standard layout).

**If monorepo:**

1. Create `/specs/projects/` in each confirmed sub-project root:

```bash
mkdir -p specs/projects
touch specs/projects/.gitkeep
```

2. Create `/specs/monorepo.md` at repo root with:
   - Sub-project names and their paths
   - Brief description of what each sub-project does
   - Ask the user for enough detail to make this useful

Example monorepo.md:

```markdown
# Monorepo Layout

This repository contains multiple projects.

## Sub-Projects

| Path | Description |
|------|-------------|
| `backend/` | Python API server using FastAPI |
| `frontend/` | React web application |
| `shared/` | Shared TypeScript types and utilities |

Projects that span multiple sub-projects should be spec'd at the repo root's `/specs/projects/`.
Projects scoped to a single sub-project should be spec'd within that sub-project's `/specs/projects/`.
```

### 4. External Knowledge Check

Check for commonly-needed project-specific configuration that lives in the user's system prompt (CLAUDE.md, AGENTS.md, etc.). Suggest additions if missing.

Look for evidence of:

| Item | What to look for |
|------|------------------|
| Automated check / CI command | `checks.sh`, `npm test`, `pytest`, `cargo test --all-targets`, etc. |
| Test framework | References in code or config files |
| Linting / formatting | `.eslintrc`, `pyproject.toml` (ruff, black), `golangci.yml`, etc. |
| Code review guidelines | `.agents/code_review_guide.md`, `docs/cr.md`, etc. |
| Code style conventions | Style guides linked in config |

Also try to detect the agent tool in use:
- `.cursor/` → Cursor
- `CLAUDE.md` or `.claude/` → Claude Code
- `AGENTS.md` or `.codex/` → Codex
- (Other tool markers)

Use the detected tool name in suggestions if known. Fall back to "your agent's system prompt configuration."

**For each missing item, provide:**

1. Where to add it (e.g., "Add to CLAUDE.md or AGENTS.md")
2. A template snippet

Example suggestions:

```markdown
### Suggested Addition: Automated Checks

I don't see automated check commands configured for this project. Add something like this to your CLAUDE.md or AGENTS.md:

```markdown
## Automated Code Checks

Run all automated checks with:
- Python: `uv run pytest && uv run ruff check . && uv run mypy .`
- JavaScript: `npm test && npm run lint`
```

This ensures the coding agent runs tests, linting, and type-checking before finishing a phase.
```

### 5. Completion

Summarize what was done:

```
Setup complete:
- Added .specs_skill_state/ to .gitignore
- Created /specs/projects/ directory (with .gitkeep)
- [Created /specs/projects/ in sub-project roots if monorepo (with .gitkeep)]
- [Created /specs/monorepo.md if monorepo]
- [Suggestions for external knowledge configuration]

You're ready to run `/spec new_project` to start your first spec'd project.
```

## Notes

- **Idempotent**: Can run multiple times safely. Only adds what's missing.
- **Incremental**: If you add new sub-projects later, re-run setup to extend the structure.
- **Non-destructive**: Never modifies or deletes existing content.
