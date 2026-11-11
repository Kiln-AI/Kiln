---
name: docs-sync
description: Find and fix the docs and agent guidance that a branch makes stale - agent skills and their reference files, AGENTS.md and .agents/*.md prompts, READMEs, docs/ folders, and code-adjacent docs that name a changed path, command, symbol, env var, setting, endpoint or behaviour. Use before opening a PR, before pushing new commits to an open PR, and when asked to update docs or skills after a change. The open-pr skill runs it every time.
---

# Docs sync: keep docs and skills true to the code

A change that renames a script or removes a function leaves every doc that names it wrong, and the next agent follows the wrong doc. Run this before you open a PR and before each push to an open PR. It finds what changed, finds the docs that mention it, and fixes them in the same PR.

Run every command from the repo root. Shell variables do not carry over between commands: run each code block as one command.

## 1. Find what changed

```bash
BASE=$(gh pr view --json baseRefName --jq .baseRefName 2>/dev/null) || BASE=<the base from open-pr Step 2, else main>   # no PR yet
git fetch -q origin "$BASE"; B="origin/$BASE"
git diff --name-status -M "$B"...HEAD    # A/M/D/R per file
git log --format='%h %s%n%b' "$B"..HEAD   # intent, new conventions
git diff -U0 "$B"...HEAD | grep -E '^[-+](\s*(async )?def |\s*class |export (async )?(function|const|class|type|interface|enum) |\s*@app\.(get|post|put|patch|delete)\()|os\.(environ|getenv)|env_var=|process\.env|import\.meta\.env'
git diff -U0 "$B"...HEAD | grep -E '^@@' | sed -E 's/^@@ [^@]* @@ ?//' | sort -u   # functions and classes whose bodies changed
git diff --stat "$B"...HEAD -- '*.sh' '*pyproject.toml' '*package.json' .github/workflows .agents
```

Turn that output into a list of search terms. Use the old name; for a rename, the new name is the replacement.

- Each A, M, D and R file: its full repo path and its file name with the extension. For a Python file, also its dotted import path (`app.desktop.desktop_server`; under `libs/`, start at the package: `kiln_ai.adapters.ml_model_list`). Do not use bare stems such as `utils` or `config`.
- Each rename or move: the old path too. When a whole directory moved, add the old directory path.
- Each M file: the names of the functions and classes from the `@@` hunk headers (a header names the nearest earlier top-level line, not always the changed one), and the key nouns of the commit subjects. These find the docs that describe the changed behaviour, not only the docs that name the file.
- Each removed or renamed public symbol: a `def`, `class` or export on a `-` line with no matching `+` line.
- Each removed, renamed or added env var, setting, endpoint path, CLI command, script, check or CI workflow.
- Each new convention or gotcha (a new place where a kind of file goes, a new required step, a new command). These have no old name to search; note the area they belong to.

## 2. Find the docs that mention them

```bash
TERMS=(-e app/desktop/old_script.sh -e old_script.sh -e old_function)   # one -e per term from step 1
DOCS=(AGENTS.md .agents '*.md' '*.mdx' .github .config)
NOT_DOCS=(':!AGENTS.md' ':!.agents' ':!*.md' ':!*.mdx' ':!.github' ':!.config')
SKIP=(':!specs/projects' ':!.agents/playwright_project' ':!*kiln_ai_server_client*' ':!app/web_ui/src/lib/api_schema.d.ts')
git grep -n -F "${TERMS[@]}" -- "${DOCS[@]}" "${SKIP[@]}"            # docs, skills, prompts, configs
git grep -n -F "${TERMS[@]}" -- . "${NOT_DOCS[@]}" "${SKIP[@]}"      # code-adjacent mentions
```

- The first grep covers skills and their reference files and scripts, `AGENTS.md`, `.agents/*.md` prompts, every README, `docs/`, `app/*/docs/`, the PR template, CI workflows and `.config/`.
- The second grep covers everything else: comments, docstrings, `--help` and usage text, the `Makefile`, `pyproject.toml` scripts, and the scripts that skills link to.
- If you work on an active spec project, add `specs/projects/<project>` to both greps.
- Add `-w` for short symbol names that match inside longer names. Add `-i` for terms that docs write in prose.
- For a new convention or command from step 1, find its closest home: `git grep -n -l -i '<area word>' -- AGENTS.md .agents '*.md' '*.mdx' .github .config`, and read the `description` lines in `.agents/skills/*/SKILL.md`.

Read each hit. Judge whether the text describes the changed behaviour, not only whether the name matches. Each hit gets a decision in step 3.

## 3. Update each stale statement in place

- Rewrite the sentence, command, path or table row so it describes the code as it is now. Point to the replacement when one exists. Delete the statement when nothing replaces it.
- Add guidance where the change introduces something a future agent must know: a new gotcha, a new "where things go" rule, a new command or check. Put it in the closest existing skill, reference file or prompt. Create a new file only when nothing fits.
- When a hit is still true (a different thing with the same name, or a historical mention in a commit or spec), leave it and note why.
- Match the style of the file you edit. `open-pr` and other files written in Simplified Technical English stay in it.

## 4. Do not make these edits

- Do not rewrite docs that the change did not make stale.
- Do not edit generated files: `CLAUDE.md`, `.claude/`, `.cursor/`, `.mcp.json`, `.worktreeinclude`, the generated API client under `kiln_ai_server_client/`, `app/web_ui/src/lib/api_schema.d.ts`. Edit their sources (`AGENTS.md`, `.agents/`, `.config/wt/`).
- Do not touch the human header of `.github/pull_request_template.md` (everything above `# Agentic PR Summary`). If it holds stale text, tell the user in your end-of-task summary.
- Do not add history to docs: no "renamed from", "previously", "as of" or changelog notes. Docs describe the current state.
- Do not edit anything under `specs/projects/**` except the active project's own files.

## 5. Commit and report

Commit the doc updates in the same PR, as their own commit:

```bash
git add <doc files>
git commit -m "docs: <what the docs now say>"
```

Re-run your agent setup script if you changed `.agents/`.

When the PR has an Agentic PR Summary, add one line to it, or update the line that is there. List every doc file that the PR changes:

- `**Docs and skills updated:** <files>, <one-line reason>.`, or
- `**Docs and skills updated:** none needed, <one-line reason>.`

## 6. Done when

- You looked at every hit from step 2 and updated it or noted why it stays.
- Nothing left refers to a removed path or symbol. This final check prints only the hits that you noted as still true:

```bash
git grep -n -F -e <removed path> -e <removed symbol> -- . ':!specs/projects' ':!.agents/playwright_project' ':!*kiln_ai_server_client*' ':!app/web_ui/src/lib/api_schema.d.ts'
```

Add the active spec project back to that check if you work on one.
