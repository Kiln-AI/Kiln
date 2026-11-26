---
status: complete
---

# Phase 6: The knowledge tooling port, the maintenance skill and the knowledge backlog

## Overview

Port harness-tuner's knowledge tooling (`src/kiln_harness_tuner/knowledge/` at `b49f159`) into `kiln_mcp_server/skill_checks/`, so that the knowledge trees (`references/levers/`, `references/improving_agents/`) that the content phase imports have a checker and an index builder from the first batch. Add the `build` command to the skill-checks CLI (knowledge index blocks and `docs_index.md`), the `make skill_index` target, the `knowledge-maintenance` skill for coding agents, and the knowledge backlog with its format test and the new `using_harness_tuner` entry. The knowledge trees themselves are not imported here (content batch 7), so the shipped tree has no knowledge yet and every knowledge check must pass on a skill without it.

Spec: [skill_and_content](../components/skill_and_content.md) sections 1, 5, 7 and the step-5 rows of 10; architecture sections 2, 6 (step 5), 9.2 and 11 (item 2). Carried from phase 5: `Problem` moves into `knowledge_schema.py`, `default_root()` has one definition, the `build` command, `make skill_index`, and the fix command of the AGENTS.md skill-tree row.

## Steps

1. **`skill_checks/front_matter.py`** (new): `FrontMatter(present, data, error, body)` and `read_front_matter(text)`. One parser for the tree check, the knowledge loader and the docs index. It catches the `ValueError` that the YAML loader raises for an impossible date.

2. **`skill_checks/knowledge_schema.py`**: `COMPONENT_ROOTS`, `INDEX_BLOCKS`, `API_DOCS_PREFIX`, `API_CATALOGUE_SUFFIX`, `BUILD_COMMAND`, `TASK_SHAPES`, `MAX_CHARS`, `REQUIRED_SECTIONS` (lever heading `How to change it`), `EVAL_STANCES`, `PRIOR_SOURCES`, `NO_PRIORS`, the id patterns, `PlaybookKind`, `utc_today()` (`timezone.utc`), `default_root()` (moved from `tree_check`), `Problem` (moved from `tree_check`), `AppliesTo`, `CommonMeta`, `LeverMeta(api_docs)`, `TechniqueMeta`, `PlaybookMeta`, `SmellMeta` (no `detected_by`, no `detectors`), `META_MODELS`.

3. **`skill_checks/knowledge_load.py`**: `Link(target, resolved: str | None, external)`, `Section`, `Document(path: str, kind, id, meta, sections, links, chars, text, problems)`, `KnowledgeBase(root, documents, other_files: tuple[str, ...])`, `resolve_link(target, tree) -> str | None` (exact lookup; a `.` or `..` part does not resolve), `load(root=None)` over `skill_files.list_tree`, `document_kind(key)` (`index` for an `INDEX_BLOCKS` file, a component key directly in its root, `subfile` deeper), `component_root_of(key)`, `fence_marked(text)`. Other files: non-documents under `references/levers/`, `references/improving_agents/`, or directly in `references/`.

4. **`skill_checks/knowledge_index.py`**: `read_block`, `replace_block`, `render_blocks(kb)` with the blocks and columns of section 7 (first cell the full path in backticks; `levers` with `API docs`; `techniques` active only; `techniques-dormant`; `smells`; `playbooks-<kind>`), `write_blocks(kb) -> list[Path]` (bytes, so line ends stay LF).

5. **`skill_checks/knowledge_check.py`**: `check(kb, *, tree) -> list[Problem]` with the 19 rules of section 7: `front-matter`, `id`, `sections`, `placeholder`, `size`, `shape`, `link` (from the skill root), `technique-lever-ids`, `lever-api-docs` (prefix, in the tree, an endpoint doc and not a catalogue or `api_index.md`), `technique-lever-links`, `technique-stance`, `technique-priors`, `playbook-priors`, `alternatives`, `playbook-steps`, `smell-remedies`, `subfile`, `index` (the blocks of `INDEX_BLOCKS`; a missing index file is a problem only when its folder holds files, so a skill without a knowledge tree passes), `stray`. `KNOWLEDGE_RULES` lists the rule ids and `encoding`.

6. **`skill_checks/docs_index.py`**: `render_docs_index(tree_root) -> str` (section 7 format), `write_docs_index(tree_root) -> Path | None`, `docs_index_problems(tree_root)` (rule `docs-index`). No index is wanted when the skill has no help article and no index file.

7. **`skill_checks/tree_check.py`**: import `Problem`, `default_root` and the front-matter parser from the new modules; `KNOWLEDGE_DOCUMENT_FOLDERS` and `NO_FRONT_MATTER_FILES` from `COMPONENT_ROOTS` and `INDEX_BLOCKS`. `app/desktop/skill_api_reference.py` imports `default_root` from `knowledge_schema`.

8. **`skill_checks/__main__.py`**: `run_check(root)` (tree, knowledge, docs index) and `run_build(root)`; commands `check` and `build` (`rewrote <file>` per changed file, then the check). Exit codes as before.

9. **`.agents/skills/knowledge-maintenance/`**: `SKILL.md` ported with the edits of section 7 (paths and commands; any agent on the Kiln MCP reads the knowledge; "nothing measured on a user's project or on a demo project"; the language rule covers the two trees; the backlog procedure with the new path and its pytest command; section 8 unchanged; the procedure to port fixes from harness-tuner with the recorded commit `b49f159…`), `templates/` (lever with `api_docs` and `How to change it`, smell without detector keys, links as full root paths), `references/schema.md` (the schema part of harness-tuner's design document, for Kiln's layout).

10. **`app/mcp/knowledge_backlog.md`**: harness-tuner's `specs/backlog.md` at `b49f159`, with the rule of section 7: 67 entries come over (5 ranked), 20 stay behind, 1 is dropped. `tuner` leaves the `Where` of a mixed entry; the five teachable `tuner` gaps get `Where: knowledge`; links into harness-tuner become short references in words; role and loop words in the text get the wording rules. The header states the Kiln format (`Kind` adds `guide`, drops `detector`; `Where` is `knowledge` or `kiln`). `using_harness_tuner` is the last entry of `Unranked`.

11. **Wiring**: `Makefile` target `skill_index`; the AGENTS.md skill-tree row gets `make skill_index` as its fix and names the knowledge; one AGENTS.md line names the `knowledge-maintenance` skill and the approval rule.

## Tests

- `skill_checks/test_knowledge_check.py` (port of harness-tuner's `tests/test_knowledge_checks.py`; synthetic skill through `build_tree`, full root paths): one test per rule (front matter cases, review-date tolerance, ids, sections and the old lever heading, placeholders, size, shape, links not written from the root, case, fences, `resolve_link`, lever ids and links, `lever-api-docs` cases, stance, priors, alternatives, playbook steps, smell remedies, the removed smell keys, sub-files, index, missing index file, strays), plus `test_a_valid_minimal_tree_passes_the_tree_check`, `test_a_skill_with_no_knowledge_tree_has_no_problem`, the block renderings and `build` keeping text outside the markers.
- `skill_checks/test_knowledge_backlog.py` (port of `tests/test_backlog.py`): the real file has no problem of any rule; one violation per rule on a small text, with a `detector` kind and a `tuner` where; `test_the_backlog_is_outside_the_package`; `test_the_using_harness_tuner_entry_is_last_in_unranked`.
- `skill_checks/test_docs_index.py`: `test_render_docs_index`, `test_write_docs_index_writes_and_then_reports_no_change`, `test_a_stale_docs_index_is_reported`, `test_no_docs_index_without_help_articles`.
- `skill_checks/test_main.py`: `build` rewrites the indexes then checks; `build` on a current tree prints nothing; `check` reports a stale knowledge index; `build` with a missing folder exits 2.
- `skill_checks/test_shipped_skill.py`: `test_the_shipped_knowledge_passes_every_check`, `test_the_full_check_passes`, `test_pending_rules_are_known_rules`, `test_each_template_gives_a_valid_document` (also passes the tree check), `test_each_template_has_the_required_headings_and_front_matter_keys`, `test_the_maintenance_skill_names_the_commands` (with the backlog path and its test command), `test_the_maintenance_skill_names_its_folder`, `test_the_maintenance_skill_is_inside_its_line_limit`, `test_the_maintenance_skill_links_resolve`, `test_agents_md_points_to_the_maintenance_skill`.
