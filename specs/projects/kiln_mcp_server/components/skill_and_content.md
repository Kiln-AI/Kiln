---
status: complete
---

# Component: Skill and content

Covers the `kiln_skill` tool, the skill tree and its packaging, the API reference pipeline, the knowledge tooling and the knowledge backlog, the skill-tree check, and the content port with the merge of its two sources. Spec sections: [functional_spec.md](../functional_spec.md) 6, 7, 16. The server, the PyInstaller hook with its test, and the module `texts.py` are in [mcp_server_and_api_tool](mcp_server_and_api_tool.md) (the server doc below). The MCP block list is section 6 of that doc. Cross-cutting decisions, shared files and the build order are in [architecture.md](../architecture.md).

## 1. Files

```
app/mcp/kiln_mcp_server/
  skill_files.py            index, path resolution, read, address replacement, API_CATALOGUE_INDEX_PATH.
                            No MCP SDK import.
  skill_tool.py             the tool function and register_skill_tool()
  texts.py                  server doc 2.4; holds SKILL_TOOL_DESCRIPTION and PATH_DESCRIPTION (2.2)
  skill/                    THE SKILL ROOT. Package data. Markdown only. No __init__.py.
  skill_checks/             dev tooling. The server never imports it, so PyInstaller leaves it out.
    __main__.py             CLI: check | build
    tree_check.py           section 8
    knowledge_schema.py  knowledge_load.py  knowledge_check.py  knowledge_index.py     section 7
    docs_index.py           online_url_for(), render_docs_index()
    test_knowledge_backlog.py   the format of app/mcp/knowledge_backlog.md (section 7)
    api_reference.py        render / write / diff of api_docs from a spec dict (section 6).
                            It never imports app.desktop; the spec is built in app/desktop.
  test_*.py                 beside each module
app/mcp/knowledge_backlog.md   the knowledge backlog (section 7). Beside the package, not inside it,
                            so it is not bundled and no agent on the MCP reads it
app/desktop/
  skill_api_reference.py    CLI generate | check: builds the OpenAPI document in process
  test_skill_api_reference.py
.agents/skills/knowledge-maintenance/     SKILL.md, templates/, references/schema.md
.gitattributes              app/mcp/kiln_mcp_server/skill/** text eol=lf
```

## 2. The `kiln_skill` tool

### 2.1 Registration

```
SKILL_TOOL_NAME = "kiln_skill"

def register_skill_tool(mcp: FastMCP, *, bound_host: str, bound_port: int) -> None

@mcp.tool(name=SKILL_TOOL_NAME, description=SKILL_TOOL_DESCRIPTION, structured_output=False,
          meta={"anthropic/alwaysLoad": True},
          annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False))
async def kiln_skill(                 # no Context argument: the tool uses no request data
    path: Annotated[str | None, Field(description=PATH_DESCRIPTION,
                                      validation_alias=AliasChoices("path", "resource"))] = None,
) -> CallToolResult
```

- `register_skill_tool` computes the app address once, `origin = app_origin(bound_host, bound_port)` (`addresses.py`, server doc 2.3), and the tool function uses it for every call.
- Start check. The server builder calls `register_skill_tool` once and, after both tools are registered, `skill_files.get_index()` (server doc 2.1, step 6). `build_index` raises `RuntimeError("Kiln skill files are missing from the package (no SKILL.md)")` when the tree has no `SKILL.md`, so such a package fails at start, not at the first call.
- Published schema: one property `path` (string or null, default null), and no `required` key (SDK 1.30 writes none when no argument is required). `resource` is accepted and not published. FastMCP drops unknown arguments, so `name`, `skill` and `id` are ignored with any value.
- `meta` reaches `tools/list` as `_meta`. It asks Claude Code to load the tool definition up front. Agents that ignore it see the same trigger text in the server `instructions` (server doc 2.4). `SKILL_TOOL_DESCRIPTION` and the instructions state the same three facts: what Kiln is, call `kiln_skill` first, `/kiln` means call it.
- The annotations (`readOnlyHint`, `idempotentHint`, `openWorldHint=False`) are a decision: they are true, and they let an agent skip a permission prompt.
- Every result is `CallToolResult(content=[TextContent(type="text", text=...)], isError=...)`. A raised exception would get the SDK prefix `Error executing tool kiln_skill: `, so `SkillPathError` is caught and returned with `isError=True`.
- A `path` that is not a string is refused by the SDK's own validation (its text, `isError`). Nothing else uses SDK text.

### 2.2 Texts

Both constants live in `kiln_mcp_server/texts.py` with the server instructions and the `call_kiln_api` description (server doc 2.4). `skill_tool.py` imports them. Batch 14 of the content phase tunes all of them (section 9).

`PATH_DESCRIPTION` (functional spec 6.1):

```
Optional. The path of a skill file to read, relative to the skill root and exactly as the skill's instructions wrote it, for example `references/knowledge/specs_and_evals.md`. Omit it to read the skill's instructions.
```

`SKILL_TOOL_DESCRIPTION` (draft, 136 words; the trigger rule ends at character 447, inside the first 500). Its second paragraph starts with the shared opening `WHAT_KILN_IS` and a full stop; the code builds the text from that constant, so the opening cannot differ from the one in the server instructions:

```
Load the Kiln skill: the instructions for working with Kiln.

Kiln is an app for building, evaluating and optimizing AI agents. This skill says what Kiln can do, how to call its API with `call_kiln_api`, and how to make an agent better. When a request involves Kiln, call this tool first, before any other Kiln tool, and follow what it returns. Users may also ask for it by name (`/kiln`, or "the Kiln skill"); that is a request to call this tool.

- No arguments: returns the skill's instructions. They list the reference files.
- `path`: returns one reference file. Copy the path exactly as the instructions wrote it, for example `references/knowledge/specs_and_evals.md`.

Only paths the instructions list are valid; do not guess. If the instructions are no longer in this conversation, call again with no arguments.
```

### 2.3 Index

```
DEFAULT_ORIGIN = "http://localhost:8757"
API_CATALOGUE_INDEX_PATH = "references/knowledge/api_docs/api_index.md"     # final name; the pipeline writes it (section 6)

@dataclass(frozen=True)
class SkillIndex:
    files: dict[str, Traversable]     # key: POSIX path from the skill root, e.g. "references/knowledge/rag.md"
    folders: frozenset[str]           # every ancestor of every file; "" is the root

class SkillPathError(Exception)       # .message is the full error text

def build_index(root: Traversable | None = None) -> SkillIndex
def get_index() -> SkillIndex                                  # functools.lru_cache(maxsize=1)
def resolve_path(raw: str | None, index: SkillIndex) -> str | None     # None = the root instructions
def read_file(key: str, index: SkillIndex) -> str
def strip_front_matter(text: str) -> str
def apply_origin(text: str, origin: str) -> str
def read_skill(raw: str | None, origin: str, index: SkillIndex | None = None) -> str
```

- `API_CATALOGUE_INDEX_PATH` is the one definition of the catalogue index path. The `call_kiln_api` error texts use it (server doc 4.3), and so does `skill_checks/api_reference.py`. `test_the_catalogue_index_exists` checks that it is a file of the shipped tree (section 10).
- Root: `importlib.resources.files("kiln_mcp_server").joinpath("skill")`. Use only `files`, `iterdir`, `is_dir`, `is_file`, `name`, `read_bytes` and single-segment `joinpath` (all in 3.10). Import `Traversable` from `importlib.resources.abc` on 3.11+, else `importlib.abc`.
- Walk: depth first, skip names that start with `.` and `__pycache__`; build each key by joining names with `/`. Sort the keys. No OS path is ever built from tool input. The index is immutable after the build, so concurrent calls need no lock.
- `read_file`: `index.files[key].read_bytes().decode("utf-8")`. No newline translation.

### 2.4 Path resolution

`resolve_path(raw, index)`, in this order:

1. `raw is None` → root.
2. `p = raw.strip()`. If `p` has 2+ characters and starts and ends with the same one of `` ` `` `'` `"`, drop that pair and strip again. `p == ""` → root.
3. Any character below U+0020 in `p` → `E_CTRL`.
4. `p` starts with `skill://` (any case): take the text after it; split at the first `/`; if the first part is not `kiln` (any case) → `E_SKILL`; continue with the rest. Else if `p` matches `^[A-Za-z][A-Za-z0-9+.-]*://` → `E_SCHEME`.
5. Replace `\` with `/`. Cut at the first `#`, then at the first `?`.
6. `p` starts with `/` or `~`, or matches `^[A-Za-z]:` → `E_ABS`.
7. Split on `/`. Drop `""` and `.` segments. A `..` segment → `E_UP` (always, also `a/../b`).
8. `key` = the segments joined with `/`. `key` is `""` or `SKILL.md` → root.
9. `key in index.files` → that file. Else → `E_MISS`.

No percent-decoding. Matching is exact and case-sensitive on every OS.

| Input (`path` unless noted) | Result |
|---|---|
| absent, `null`, `""`, `"  "`, `SKILL.md`, `./SKILL.md`, `skill://kiln`, `skill://kiln/SKILL.md` | root |
| `{"name": "kiln"}`, `{"skill": "kiln", "id": "x"}` | root |
| `references/knowledge/rag.md` | that file |
| `./references/knowledge/rag.md`, `skill://kiln/references/knowledge/rag.md`, `references\knowledge\rag.md`, `` `references/knowledge/rag.md` ``, `references//knowledge/rag.md`, `references/knowledge/rag.md#setup` | the same file |
| `{"resource": "references/knowledge/rag.md"}` | the same file |
| `/etc/passwd`, `~/x`, `C:\x`, `\\host\share` | `E_ABS` |
| `../x`, `references/../SKILL.md` | `E_UP` |
| `https://x/y.md` | `E_SCHEME` |
| `skill://other/x.md` | `E_SKILL` |
| `References/Knowledge/RAG.md` | `E_MISS` with "Did you mean" |
| `references/knowledge`, `references/knowledge/` | `E_MISS` with "is a folder", lists that folder |
| `references/nope/deeper/x.md` | `E_MISS`, lists `references` |
| `references/knowledge/api_docs/get_api_nope.md` | `E_MISS`, short API listing |
| `{"path": 5}` | SDK validation error |

### 2.5 Error texts

`{raw}` is the argument as received, with backticks and control characters removed, cut to 200 characters. Square brackets mark a part that is present only when it applies.

```
HINT     = "Give a path relative to the skill root, exactly as the skill's instructions wrote it, for example `references/knowledge/specs_and_evals.md`. Omit the path to read the skill's instructions."
E_ABS    = "Refused: `{raw}` is an absolute path. " + HINT
E_UP     = "Refused: `{raw}` leaves the skill root. `..` is not allowed in a skill path. " + HINT
E_SCHEME = "Refused: `{raw}` is not a skill path. " + HINT
E_SKILL  = "Refused: `{raw}` names another skill. This tool serves one skill, `kiln`. " + HINT
E_CTRL   = "Refused: the path holds a control character. " + HINT

E_MISS =
No skill file at `{raw}`.[ Did you mean `{ci}`?][ `{key}` is a folder, not a file.]
Files in {where}:
{one full path per line, sorted; "(none)" when empty}
[Folders in {where}:
{one full path per line, each with a trailing "/"}]
Copy a path exactly as the skill's instructions wrote it.
```

- `{ci}`: the first key equal to `key` when both are lower-cased. `{where}`: the nearest existing folder in backticks, or `the skill root`. The nearest folder is the longest prefix of `key`'s segments that is in `index.folders` (`key` itself when it is a folder). Only direct children are listed.
- When the nearest folder is `references/knowledge/api_docs`, list only `api_index.md` and the `*_api_list.md` files, then the line `Plus {n} endpoint docs, not listed. Find an endpoint doc through a catalogue.` (the full listing is about 15 KB).
- Two deliberate choices beyond functional spec 6.1, both accepted. The error lists the sub-folder names of the nearest folder as well as its files, so the agent can correct a wrong folder in one step; it is still an error, not a folder listing. The listing of `api_docs` is shortened to the catalogue index and the catalogues, because the full listing of about 295 files would flood the agent's context.

### 2.6 What is returned

- Root: `strip_front_matter(SKILL.md)`. If line 1 is exactly `---` and a later line is exactly `---`, return the text after that line with leading blank lines removed. Otherwise the text is unchanged.
- A reference file: the whole text, front matter included. The help articles carry `online_url` there, and the knowledge documents carry `levers`, `cost` and `applies_to`, which the agent uses. This is deliberate and matches functional spec 6.1, which leaves front matter out only for the root `SKILL.md`.
- No header and no footer (functional spec 6.1).
- App address. The rule is architecture section 3, item 11. `origin` is the value that `register_skill_tool` computed at registration with `app_origin(bound_host, bound_port)` (server doc 2.3): `http://localhost:<port>` for a loopback or wildcard bind, `http://<host>:<port>` for a specific non-loopback host. The tool never reads the request: not its Host header, not its scheme. Then `apply_origin(text, origin)`: when `origin != DEFAULT_ORIGIN`, `text.replace("http://localhost:8757", origin)`; otherwise no change. It applies to every served file and to nothing else.
- Because no request data is used, a forwarded port or a proxy in front of Kiln needs no special handling: the links name the address on Kiln's machine. With a wildcard bind the links name `localhost`. Both are accepted (architecture section 3, item 11).

## 3. Layout and bundling

```
skill/
  SKILL.md
  references/
    modes/*.md
    knowledge/*.md                      hand-written; includes memory.md, train_val_test.md,
                                        working_with_project_files.md, code_tool_authoring.md,
                                        run_an_experiment.md, diagnose_an_agent.md (section 9.3)
    knowledge/code_tool_wrappers/*.md   one wrapper template per file, as a fenced block
    knowledge/api_docs/*.md             generated, committed (section 6)
    docs/**/*.md  docs/docs_index.md    copied help articles; generated index
    levers/*.md  levers/index.md
    improving_agents/index.md
    improving_agents/{techniques,smells,playbooks}/**/*.md
```

- Every file is Markdown, UTF-8, LF. File and folder names match `^[A-Za-z0-9_.-]+$`. No Python file sits in the tree, so `ruff`, `ty` and pytest collection skip it.
- Wheel: hatchling includes every file under the package folder. No config.
- PyInstaller does not collect package data by itself. The server doc owns the fix and its one test: the hook file `hook-kiln_mcp_server.py` with `collect_data_files("kiln_mcp_server")`, and the test in `app/desktop/test_pyinstaller_hooks.py` that the collected files match the skill file index (server doc, sections 1 and 10). This doc adds no build change and no second test. The start check in 2.1 is the guard at run time.
- **Placeholder tree.** From build step 1 until the content phase (step 6), `skill/` holds a placeholder: one minimal hand-written `SKILL.md` that says what Kiln is and that the full skill is not in this build. It satisfies the start check and the bundling test. In step 4 it gets one line that names `references/knowledge/api_docs/api_index.md`, so that the generated folder is reachable. Batch 1 of the content phase replaces it.
- The wrapper templates of `code_tool_wrappers/` are Markdown with a fenced block, not `.py` files, so that the tree stays Markdown only. They lose lint and unit tests; a compile check remains (`test_wrapper_templates_compile`). Accepted.

## 4. Content model

### 4.1 Conventions (C1–C7 have a check in section 8; C10 has a test in section 10; C8, C9, C11 and C12 are review rules, with the checks they name; C13 has a check in section 8 for its mechanical part and is a review rule for the rest)

| # | Rule |
|---|---|
| C1 | A reference to a skill file is the full path from the skill root, in backticks or as a Markdown link target: `references/knowledge/rag.md`. No bare file name, no `./`, no `../`. |
| C2 | No call syntax and no mention of the skill tool: the strings `skill(name=` and `kiln_skill` never occur. `call_kiln_api` may be named. |
| C3 | Every file is reachable from `SKILL.md`. A hand-written file is listed by `SKILL.md` or a mode with its full path and one line: what it holds and when to read it. |
| C4 | A page of the Kiln app is written as `http://localhost:8757/<path>`, in rule statements, tables and examples. Placeholders are `{project_id}`, `{task_id}`. Never a bare app path, never another host. |
| C5 | A placeholder path contains one of `* < > { }` or ends in `X.md`. It is not a reference. |
| C6 | No file names a tool, role or folder that does not exist on this MCP (banned terms, section 8). |
| C7 | Only `references/knowledge/train_val_test.md` states the train/val/test rule. A mode or knowledge-tree file that uses split wording names its path. |
| C8 | Help articles are copies. A one-off import script, run in the content phase and not kept in the repository, adds `online_url`, rewrites links and removes images (batches 1 and 6). After that the only hand edits are spelling fixes. `tree-front-matter` then enforces that every help article has its `online_url`. A later refresh of the copies is a follow-up (architecture section 8). |
| C9 | The two knowledge trees (`references/levers/`, `references/improving_agents/`) follow the knowledge schema (section 7) and are written in Simplified Technical English. The rest of the skill has no language rule. |
| C10 | For a capability whose endpoint is MCP-blocked, the text says "ask the user to do this in the app" and gives the link to the app page of 4.4. No hand-written file names the path of a blocked endpoint. The same wording is used when an API error says that Kiln Pro or a provider is not connected. |
| C11 | **A port, not a redesign of the method.** The method of the knowledge is harness-tuner's, ported as it is: no rule is loosened, extended or added. Only vocabulary changes. The Assistant's content stays as "how to do it in Kiln". The full rule is 4.5. |
| C12 | Each question has one owner (the five owners, 4.5). Only `references/knowledge/run_an_experiment.md` states how a change is measured, judged and kept. Another file names its path. |
| C13 | No file selects, compares or keeps a candidate on the test split: these use train and val, as `references/knowledge/train_val_test.md` states. No file asks for the test split in a call. A file that names a call or an app page that reads the test split when no split is asked for says which split it reads and how to ask for train or val, or names the path of the file that does. |

### 4.2 Front matter by file type

| Files | Front matter | Served |
|---|---|---|
| `SKILL.md` | `name: kiln`, `description` (1–1024 characters): a valid Agent Skill | removed |
| `references/modes/*.md`, hand-written `references/knowledge/**/*.md` | exactly `name` (the file stem) and `description` | kept |
| `references/knowledge/api_docs/*.md` | none (as generated) | — |
| `references/docs/**/*.md` except the index | as copied, plus `online_url` equal to `online_url_for(path)` | kept |
| `docs_index.md`, `levers/index.md`, `improving_agents/index.md` | none | — |
| Levers, techniques, playbooks, smells | the knowledge schema, unknown keys refused | kept |
| Technique sub-files | none | — |

`online_url_for`: `references/docs/<p>.md` → `https://docs.kiln.tech/docs/<p>`; `references/docs/<folder>/README.md` → `https://docs.kiln.tech/docs/<folder>`.

### 4.3 What `SKILL.md` must contain

The agent gets it from one tool call, and it can leave the context at compaction. It has at most 300 lines and 20,000 characters, and these parts in this order:

1. What Kiln is, in three sentences. The rules below apply only while the agent does Kiln work.
2. How to read files: paths are from the skill root; give a path to the tool that returned this text; only listed paths exist; when this text is no longer in the conversation, load it again before more Kiln work.
3. Routing: one row per mode with its full path and when to read it. The routing table stays here; `references/modes/establish_intent.md` keeps only the steps for an unclear request.
4. API rules for `call_kiln_api`: read the endpoint doc before the first call to an endpoint; start from `references/knowledge/api_docs/api_index.md`; a non-2xx answer is data; narrow large answers with `jq_filter`, paging, or `save_to_tmpfile`; the end of an event stream does not mean success, so check status.
5. Working with the user: confirm with the user before a destructive or irreversible operation. Then the general reply rules, one line each: lead with the recommendation, be concise, match the user's scope (check completion before reporting scores), admit uncertainty.
6. Links into the app: the C4 rule and the table of main pages below.
7. Map of the other entry points, one line each: `references/docs/docs_index.md`, `references/levers/index.md`, `references/improving_agents/index.md`, `references/knowledge/run_an_experiment.md`, `references/knowledge/train_val_test.md`, `references/knowledge/memory.md`, `references/knowledge/working_with_project_files.md`, `references/knowledge/model_work.md`.
8. What the agent cannot do over MCP: the rule of C10 and the table of 4.4, in short form (capability and page).

It has no persona, no session-start steps and no "always in a mode" rule.

The table of main pages (part 6). The paths are the ones the app's sidebar links to (`app/web_ui/src/routes/(app)/+layout.svelte`); batch 4 writes the table and checks each against the routes folder:

| Page | Link |
|---|---|
| Run | `http://localhost:8757/run` |
| Dataset | `http://localhost:8757/dataset/{project_id}/{task_id}` |
| Specs and evals | `http://localhost:8757/specs/{project_id}/{task_id}` |
| Optimize | `http://localhost:8757/optimize/{project_id}/{task_id}` |
| Prompts | `http://localhost:8757/prompts/{project_id}/{task_id}` |
| Models | `http://localhost:8757/models` |
| Tools | `http://localhost:8757/tools/{project_id}` |
| Skills | `http://localhost:8757/skills/{project_id}` |
| Documents and search | `http://localhost:8757/docs/{project_id}` |
| Fine-tune | `http://localhost:8757/fine_tune/{project_id}/{task_id}` |
| Synthetic data | `http://localhost:8757/generate/{project_id}/{task_id}` |
| Background jobs | `http://localhost:8757/jobs` |
| Settings | `http://localhost:8757/settings` |

### 4.4 Blocked capabilities: what the skill says

The MCP block list is the server doc, section 6.3. The skill and that table must agree (functional spec 7.3). This table is built from its rows: every blocked capability that a user might ask for, with the app page the agent links to. The pages were looked up in `app/web_ui/src/routes/`. The rows not listed here (the OAuth callback pages, the Assistant's chat protocol, the job-events stream) are nothing a user asks an agent for, and the skill does not mention them.

| Capability | Block list rows | The skill says: ask the user to do this in the app, at |
|---|---|---|
| Connect or disconnect a provider API key | 26, 27 | `http://localhost:8757/settings/providers` |
| Add or remove an OpenAI-compatible provider | 28, 29 | `http://localhost:8757/settings/providers` |
| Sign in to Kiln Pro, or fix an invalid Kiln Pro key | 19 | `http://localhost:8757/settings/providers/kiln_pro` |
| Set up git sync for a project, or import a project from a git repository | 1–11 | `http://localhost:8757/settings/import_project` |
| Read, change or remove a project's git sync settings | 12–14 | `http://localhost:8757/settings/edit_project/{project_id}` |
| Choose a project file with the file picker (import a local project) | 15 | `http://localhost:8757/settings/import_project` |
| Change a setting that has no endpoint of its own (the raw settings write) | 20 | `http://localhost:8757/settings` |
| Open the application logs | 21 | `http://localhost:8757/settings` (the row "Application Logs") |
| Open a project's folder | 22 | `http://localhost:8757/settings/manage_projects` |
| Open a document's folder, or download the original (binary) document | 23, 25 | `http://localhost:8757/docs/library/{project_id}/{document_id}` |
| Open a skill's folder | 24 | `http://localhost:8757/skills/{project_id}/{skill_id}` |

"Not connected" errors (functional spec 11 and 16). The endpoints that fix them are blocked, so the skill tells the agent what to say:

- An API error says that Kiln Pro is not connected, or that its key is not valid: tell the user which function needs Kiln Pro, and ask them to sign in at `http://localhost:8757/settings/providers/kiln_pro`. Then try again.
- No provider is connected for the model asked for (the model info endpoints show the status `not_connected`): name the provider, and ask the user to connect it at `http://localhost:8757/settings/providers`. Or offer a model that is `ready`.

This text goes in `SKILL.md` part 8 in short form, and in full in the files that batch 5 edits.

### 4.5 The governing rule and the five owners

**The governing rule (C11): this is a port, not a redesign of the method.** Harness-tuner's method was thought through and debated there. This project does not reopen it.

- The method of the knowledge (the levers, techniques, smells and playbooks, and the split rule) is ported as it is. No rule is loosened for interactive use. No rule is extended. No rule is added.
- The only rewording is vocabulary: loop roles, gateway tool names, run-folder paths and loop-only inputs become words that a general agent understands. What a rule requires does not change.
- Where a rule names a loop-only input that a general agent cannot have, the text says what the agent does to get the equivalent, or says that the rule applies when running Kiln Harness Tuner. The rule is not weakened.
- The Assistant's content survives as "how to do it in Kiln": API procedures, payloads, app links, how to talk to the user. Where an Assistant file and the knowledge both teach a method for one thing, the skill keeps the knowledge's. One case is inside "how to do it in Kiln": an API procedure that carries out one of the knowledge's own rules by hand. The example is the paired statistics call, used on train and val.
- Advice of an Assistant file that the knowledge does not have is not added to a knowledge document in this port. The batch reports it. A backlog entry for it (section 7) is the owner's decision.

Four fixed points, by the owner's ruling:

- *Noise.* Harness-tuner's recommendations stay exactly as they are. The skill adds no guidance of its own on how to read the noise of an eval, and none that makes a second, identical run config for it.
- *"Metrics only" on val.* Harness-tuner's definition, unchanged. The skill adds no ruling of its own on per-item pass or fail.
- *An eval with only a test split.* The train and val splits are added first. The agent does not go on with the test split.
- *Waiving val.* The user may waive the confirmation on val. The report is then marked "train only".

**The five owners (C12).** One owner for each question. This is the deciding rule for every overlap group of 9.1 and for the hard cases of batches 13a and 13b.

| Question | Owner |
|---|---|
| What to try, in what order, under which condition (when and why) | The playbooks, smells and techniques |
| How to change one part of a run config as an experiment: a new copy, what to copy from the parent, the limits | The lever |
| How to do it in Kiln: request bodies, name rules, known traps, app links, how to talk to the user | The Assistant's knowledge file |
| How to measure a change, judge it and keep it | `references/knowledge/run_an_experiment.md` |
| The split rule and the leak rules | `references/knowledge/train_val_test.md` |

A file that needs a statement of another owner names that owner's path. It does not state it again.

Each lever's "See also" names harness-tuner skills that are not ported. Their place is taken by the Assistant files that hold the same "how to do it in Kiln" content (batch 8; the two paths marked with a batch are added by that batch):

| Lever | "See also" |
|---|---|
| `prompt` | `references/knowledge/prompt_rewrite.md`, `references/knowledge/model_create_configs.md` |
| `model` | `references/knowledge/model_work.md`, `references/knowledge/model_create_configs.md` |
| `params`, `output_mode` | `references/knowledge/model_create_configs.md` |
| `skill` | `references/knowledge/adding_skills.md` |
| `tool_config` | `references/knowledge/tools.md`, `references/knowledge/subagents.md`, `references/knowledge/rag.md` |
| `new_tool` | `references/knowledge/code_tools.md`, `references/knowledge/code_tool_authoring.md` (batch 11) |
| every lever | `references/knowledge/run_an_experiment.md` (batch 13a) |

## 5. Commands and CI entries

| Entry | Command |
|---|---|
| Check the tree, the knowledge and the generated indexes | `uv run python -m kiln_mcp_server.skill_checks check` |
| Rewrite the generated index blocks and `docs_index.md`, then check | `uv run python -m kiln_mcp_server.skill_checks build` (`make skill_index`) |
| Regenerate the API reference | `uv run python -m app.desktop.skill_api_reference generate` (`make api_docs`) |
| Check the API reference | `uv run python -m app.desktop.skill_api_reference check` |

- `checks.sh`: add `start_check "api reference" uv run python -m app.desktop.skill_api_reference check` beside `openapi schema`. `.github/workflows/check_api_bindings.yml` (Python 3.13, Linux): the same command as a step after the annotations check. The other checks are pytest tests and run with the suite on every Python version of the matrix.
- `AGENTS.md` checks table: two rows (API reference, skill indexes), each with its fix command.
- CLIs write with `sys.stdout.write` (CI fails on `print(` in a `.py` file). Exit codes: 0 clean, 1 problems (one line each: `rule  path  message`), 2 usage or missing folder.

## 6. API reference pipeline

`kiln_mcp_server/skill_checks/api_reference.py`:

```
ALLOWED_METHODS = ("get", "post", "patch", "delete")
TARGET = "references/knowledge/api_docs"

def drop_blocked(spec: dict) -> dict
def normalise(spec: dict) -> dict
def run_generator(spec: dict, workdir: Path) -> dict[str, bytes]
def catalogue_index(spec: dict, files: dict[str, bytes]) -> bytes
def render(spec: dict) -> dict[str, bytes]                 # file name -> content
def write_folder(files: dict[str, bytes], target: Path) -> None
def diff_folder(files: dict[str, bytes], target: Path) -> list[str]   # "added x.md" / "removed x.md" / "changed x.md"
```

`app/desktop/skill_api_reference.py`: `current_spec() -> dict` and `main(argv) -> int`.

Steps of `generate` (and `check`, up to step 7):

1. `current_spec()`: set `KILN_SKIP_REMOTE_MODEL_LIST=true`, then `make_app().openapi()`. No server, no network. `--spec FILE` reads a JSON file in its place.
2. `drop_blocked`: delete each operation whose `x-mcp-policy.permission` is `deny` (the key constant comes from `kiln_server.utils.agent_checks`); delete a path item left with no operation. Then, if any remaining operation has a method outside `ALLOWED_METHODS`, stop with exit 1: `call_kiln_api` cannot call it, so it must be blocked or changed.
3. `normalise`: set `info.version` to `"0.0.0"`. The version changes at each release and must not make the folder stale.
4. Write the spec to a temp file (`json.dumps(..., ensure_ascii=False)`, path order kept).
5. `run_generator`: run `[sys.executable, "-m", "openapi2skill", "--spec", <file>, "--output", <tmp>/out]` with `PYTHONUTF8=1` and `PYTHONHASHSEED=0` (the generator iterates a set of method names, so without a fixed seed the order of a path's methods in a catalogue changes from run to run). Stop on a non-zero exit, or on a stderr line that starts with `Warning: filename collision` or `Warning: tag filename collision`. The output folder is the single child of `<tmp>/out` (its name is a timestamp). Read every file of its `reference/` folder; decode UTF-8; turn `\r\n` into `\n`. Ignore the generator's own `SKILL.md`. File names are kept as generated. Stop when the count of endpoint docs differs from the count of operations in the spec.
6. `catalogue_index`: add `api_index.md` (the base name of `skill_files.API_CATALOGUE_INDEX_PATH`). For each `*_api_list.md`, read the tag from its first line (`# <Tag> API`) and count its table rows. Rows are in the order of the spec's `tags` array:

   ```
   | Catalogue | Area | Endpoints | What it covers |
   | `references/knowledge/api_docs/projects_api_list.md` | Projects | 6 | <tag description, one line> |
   ```

7. `check`: `diff_folder` against the committed folder (same names, same bytes). On a difference, print the lines and the fix command; exit 1.
8. `generate`: `write_folder` writes to a sibling temp folder, removes the target, and renames. The folder is always replaced whole.

The folder is generated for the first time in build step 4, after the block list (step 2) and the model info endpoints (step 3), so the first version already has both. From then on, every change that alters an unblocked route regenerates it in the same change.

**Pin.** Root `pyproject.toml`: dev group entry `"openapi2skill ; python_full_version >= '3.13'"` and `[tool.uv.sources] openapi2skill = { git = "https://github.com/scosman/openapi2skill", rev = "c7c2ca55e5b5300e28678ba4e47e2ad6f5bd1d28" }`. `uv.lock` records the commit. A bump of the generator is one PR that changes the `rev` and regenerates. (This is the facts file's option A; the decisions file is silent on the method.)

**Python.** The generator's metadata needs 3.13. Below 3.13, `check` prints `skipped: the generator needs Python 3.13` and exits 0, `generate` exits 2, and the freshness test skips. A second test runs on every version and needs no generator: each unblocked operation of the app has a file with the generator's name (`<method>_<path with "/" as "_", braces removed, lower case>.md`), and no blocked operation has one. Size today: 269 operations and 26 catalogues before the block list (986 KB; largest doc 24,789 bytes). The block list removes its endpoints, and a catalogue whose endpoints are all blocked.

| Known problem | Mitigation |
|---|---|
| Output folder name is a timestamp | Take the single child of a fresh temp folder |
| The generator writes with the locale encoding and OS newlines | `PYTHONUTF8=1`, newline normalisation, `.gitattributes`; the check runs on Linux |
| A name collision only warns | Step 5 stops |
| `info.version` changes at release | Step 3 |
| A knowledge file names the doc of a blocked endpoint | The tree check fails. This coupling is wanted: fix the text (batch 5) |
| 197 of 269 catalogue rows have no description | The error-probe phase (build step 8) adds route descriptions until no row is empty, and regenerates this folder in the same change (architecture section 10) |
| The in-process spec costs about 40 s in a fresh process; an API change now touches three generated artifacts | Accepted. `--spec` exists for a faster path; the fix commands are in the checks table |

## 7. Knowledge tooling port

Source: harness-tuner `src/kiln_harness_tuner/knowledge/` (1,334 lines) and its tests, at the pinned commit of section 9. Target: `skill_checks/`. Build step 5.

```
# knowledge_schema.py
COMPONENT_ROOTS = {"levers": "references/levers",
                   "techniques": "references/improving_agents/techniques",
                   "playbooks":  "references/improving_agents/playbooks",
                   "smells":     "references/improving_agents/smells"}
INDEX_BLOCKS = {"references/levers/index.md": ("levers",),
                "references/improving_agents/index.md": ("smells", "playbooks-goal", "playbooks-order",
                    "playbooks-failure", "playbooks-eval", "playbooks-design", "techniques", "techniques-dormant")}
API_DOCS_PREFIX = "references/knowledge/api_docs/"

AppliesTo = Literal["all"] | list[str]             # "all", or a list of task shapes that is not empty
PlaybookKind = Literal["goal", "order", "failure", "eval", "design"]

class CommonMeta(BaseModel):                       # model_config: extra="forbid"
    title: str                                     # one line, 3 to 60 characters
    description: str                               # one line, 40 to 200 characters, no "|": it is an index row
    reviewed: date                                 # not later than the UTC date plus 1 day
class LeverMeta(CommonMeta):      api_docs: list[str] = []
class TechniqueMeta(CommonMeta):  status: Literal["active", "dormant"]; levers: list[str]  # at least 1
                                  applies_to: AppliesTo; cost: Literal["low", "medium", "high"]
class PlaybookMeta(CommonMeta):   kind: PlaybookKind; applies_to: AppliesTo
class SmellMeta(CommonMeta):      applies_to: AppliesTo            # detected_by and detectors are removed

@dataclass(frozen=True)
class Problem:        rule: str; path: str; message: str          # one broken rule; path from the skill root

# knowledge_load.py   (frozen dataclasses)
class Link:           target: str                  # as written in the file
                      resolved: str | None         # a tree key; None when external or not in the tree
                      external: bool = False       # the target has a scheme
class Section:        heading: str; text: str; links: tuple[Link, ...]
class Document:       path: str                    # from the skill root
                      kind: str                    # a COMPONENT_ROOTS key (a file directly in that folder),
                                                   # "subfile" (deeper), or "index" (an INDEX_BLOCKS file)
                      id: str                      # the file stem
                      meta: CommonMeta | None      # None when the front matter did not parse
                      sections: tuple[Section, ...]; links: tuple[Link, ...]
                      chars: int; text: str; problems: tuple[Problem, ...]
                      def section(self, heading: str) -> Section | None
class KnowledgeBase:  root: Path                   # the skill folder
                      documents: tuple[Document, ...]
                      other_files: tuple[str, ...] = ()        # files in the component roots that are not documents
                      def by_kind(self, kind: str) -> tuple[Document, ...]
                      def get(self, kind: str, id: str) -> Document | None

def default_root() -> Path                                     # the packaged skill folder
def load(root: Path | None = None) -> KnowledgeBase            # loads COMPONENT_ROOTS and INDEX_BLOCKS files only
def resolve_link(target: str, tree: frozenset[str]) -> str | None
# knowledge_check.py
def check(kb: KnowledgeBase, *, tree: frozenset[str]) -> list[Problem]
# knowledge_index.py
def render_blocks(kb: KnowledgeBase) -> dict[tuple[str, str], str]
def write_blocks(kb: KnowledgeBase) -> list[Path]
```

- The types above are harness-tuner's, with two changes: every path is a string from the skill root (`Document.path`, `Problem.path`, `KnowledgeBase.other_files`; harness-tuner uses `Path` values relative to `references/`), and `Link.resolved` is a tree key or `None`. `tree` comes from `tree_check.tree_paths`. The kind `"index"` replaces harness-tuner's `"entry"`.
- Links in the knowledge trees stay Markdown links, because the structure rules read sections by link. The target is the full root path: `[roll-up tool](references/improving_agents/techniques/roll-up-tool.md)`. `resolve_link` does an exact lookup in `tree`; a target with a `.` or `..` part does not resolve.
- The lever section `How the tuner changes it` is renamed `How to change it`. Other required sections, size limits, id patterns and task shapes do not change.

Rules after the port (19 of 22):

| Rule | After the port |
|---|---|
| `front-matter`, `id`, `sections`, `placeholder`, `size`, `shape` | Stay. `front-matter` uses the new models; `sections` uses the new lever heading |
| `link` | Changes: resolves from the skill root against the tree |
| `reachable`, `depth` | Go. The `index` rule gives every component a row in an index file, and the tree check covers reachability from `SKILL.md` |
| `technique-lever-ids`, `technique-lever-links`, `technique-stance`, `technique-priors`, `playbook-priors`, `alternatives`, `playbook-steps`, `smell-remedies` | Stay |
| `lever-ops` | Becomes `lever-api-docs`: each `api_docs` value starts with `API_DOCS_PREFIX`, is in the tree, and is an endpoint doc (not a catalogue, not `api_index.md`). A blocked endpoint has no doc, so a lever cannot name one |
| `smell-detectors` | Goes. A smell describes how the agent measures it; the detector registry stays in harness-tuner |
| `subfile` | Stays; the folder test uses `COMPONENT_ROOTS` |
| `index` | Changes: the blocks of `INDEX_BLOCKS` |
| `stray` | Changes: only inside the four component roots and their two parents; `index.md` is allowed |

**Output format of the generated index files.** Two kinds of output.

Blocks in the two knowledge index files. A block sits between `<!-- BEGIN GENERATED: name -->` and `<!-- END GENERATED: name -->`; the prose around the blocks is hand-written and `build` never changes it. The content of a block is a newline, one Markdown table, and a newline; a block with no row holds the line `None yet.` in place of the table. Rows are sorted by id. The first cell is the full path in backticks. A document whose front matter does not parse gets no row (the check reports it).

| Block | Header row | Cells |
|---|---|---|
| `levers` | `\| Lever \| API docs \| Description \|` | path; each `api_docs` path in backticks, comma separated, or `none`; `description` |
| `techniques` (active only) | `\| Technique \| Levers \| Applies to \| Cost \| Description \|` | path; lever ids, comma separated; `all` or the shapes, comma separated; `cost`; `description` |
| `techniques-dormant` | `\| Technique \| Description \|` | path; `description` |
| `smells` | `\| Smell \| Applies to \| Description \|` | path; applies to; `description` |
| `playbooks-<kind>` | `\| Playbook \| Applies to \| Description \|` | path; applies to; `description`; only the playbooks of that kind |

The separator row is `|---|` with one `---` per column, and each row is written `| a | b | c |`.

`references/docs/docs_index.md`, from `render_docs_index(tree_root) -> str`. The whole file is generated; it has no markers and no hand-written part:

```
# Kiln help articles

Copies of Kiln's public help pages. When you point the user at a page, give them the public URL.

| Article | Public URL | What it covers |
|---|---|---|
| [<title>](references/docs/<path>.md) | <online_url> | <description> |
```

One row per file under `references/docs/` except the index itself, sorted by path. `<title>` is the text of the article's first `# ` heading, or the file stem when it has none. `<online_url>` is `online_url_for(path)` (4.2). `<description>` is the `description` of the article's front matter on one line, or empty. A `|` in a cell is written `\|`. The file ends with one newline.

**Python 3.10.** `from datetime import UTC` becomes `timezone.utc`. `print` becomes `sys.stdout.write` / `sys.stderr.write`. The import of `install_agents` goes (`NOT_SKILL_FILES = {"__pycache__", ".DS_Store"}` is local). The lazy imports of the gateway operations and the detector registry go. The code must pass `ty check` and the repo's ruff rules (`typing.cast` is banned).

**As pytest** (in `skill_checks/`): `test_knowledge_check.py` ports `tests/test_knowledge_checks.py` (one synthetic tree per rule through `build_tree`, new paths, the three removed rules deleted, `lever-api-docs` added). `test_shipped_skill.py` holds `test_the_shipped_knowledge_passes_every_check`, `test_the_generated_blocks_are_current`, `test_a_document_of_each_type_exists`, `test_each_template_gives_a_valid_document` and `test_the_maintenance_skill_names_the_commands` (which also checks that the skill names the backlog path). `test_knowledge_backlog.py` holds the format tests of the backlog. The tests tied to roles, agent CLIs, batch plans and detectors stay in harness-tuner.

**`knowledge-maintenance` skill.** Moves to `.agents/skills/knowledge-maintenance/` with `templates/`. Edits: paths and commands; who reads the knowledge (any agent on the Kiln MCP); "nothing from the target" becomes "nothing measured on a user's project or on a demo project"; the schema part of harness-tuner's design document becomes `references/schema.md` inside the skill; the language rule covers the two knowledge trees only. The backlog procedure is kept ("Add an idea or a gap for later", and the row "an idea with no content yet" of the placement rules): its path becomes `app/mcp/knowledge_backlog.md` and its command becomes the pytest run of `skill_checks/test_knowledge_backlog.py`. Its rule stays: a new entry goes at the end of `Unranked`, and the owners rank. Section 8 of the harness-tuner skill moves unchanged: **a person approves a case study or a prior before it is committed, unless it is clearly public, with its link.** `AGENTS.md` gets one line that names the skill and this rule.

**The knowledge backlog.** Harness-tuner's `specs/backlog.md` lists the known gaps and the pending ideas of the knowledge system. It is ported, in build step 5 with the maintenance skill, to `app/mcp/knowledge_backlog.md`. The file is beside the package, not inside it: the wheel and the app bundle do not hold it, and no agent on the MCP reads it.

- *Format.* As the source: the sections `Ranked` and `Unranked`; per entry a unique title, the four fields `Kind`, `Where`, `Depends on`, `Source` in this order, and one to three lines of text of at most 100 characters each. `Where` is `knowledge` or `kiln`. `Kind` is one of gap, technique, playbook, smell, lever, code, or guide (a hand-written file of `references/knowledge/`); the kind `detector` goes, because the detectors stay in harness-tuner. `skill_checks/test_knowledge_backlog.py` ports harness-tuner's `tests/test_backlog.py` and reads the file by its path in the repository.
- *Which entries come over.* The rule: an entry stays behind when the work it asks for is only in harness-tuner's loop code. Every other entry comes over: a gap or an idea of the knowledge, or a gap of Kiln itself. Applied to the 88 entries at the pinned commit (12 ranked, 76 unranked):
  - `Where` names `knowledge` or `kiln`: the entry comes over (63 entries: 50 `knowledge`, 9 `kiln`, 4 mixed). In a mixed entry, `tuner` leaves the `Where` field.
  - `Where` is `tuner` alone and `Kind` is `code` or `detector`: the entry stays behind (17 entries: 15 code, 2 detector). They are about the loop's planner, gates, report and detectors.
  - `Where` is `tuner` alone and `Kind` is `gap` (8 entries): the rule is applied to the text. Five ask for something to be taught, so they come over with `Where: knowledge`: "Input transforms", "Sub-agents", "RAG", "The `llm` tool inside code tools", "Prompt generators and few-shot". Three are about what the loop's code or gateway reads, so they stay behind: "Structured-output mode", "The task shape for loop agents", "Multi-turn eval inputs".
  - One entry that would come over is marked done at the source ("Model and provider information"). It is dropped.

  The result: 67 entries come over, 20 stay behind, 1 is dropped. An entry keeps its section and its order, so 5 entries are ranked. A `Depends on` title that did not come over becomes `None`. A `Source` that links into harness-tuner's repository becomes a short reference in words. Role names and gateway operation names in the text get the wording rules of batch 8 (section 9). The step's pull request lists the three groups by title, so that the owner can move an entry.
- *The first new entry* is `using_harness_tuner`, at the end of `Unranked` (`Kind: guide`, `Where: knowledge`, `Source: owner`): a knowledge file, `references/knowledge/using_harness_tuner.md`, that tells a coding agent with the skill how to run the Kiln Harness Tuner CLI in place of running the experiments itself. Until that file exists, the opening part of `references/knowledge/run_an_experiment.md` names Harness Tuner, tells the agent to recommend it to the user, and gives no CLI steps (section 9.3).

## 8. The skill-tree check

`tree_check.py`, over the packaged files:

```
def tree_paths(root: Path) -> frozenset[str]
def paths_in(text: str, *, file: str, tree: frozenset[str]) -> list[PathRef]   # PathRef(line, raw, path, is_folder, source)
def check_tree(root: Path) -> list[Problem]
```

**Path extraction**, per line, fenced blocks included:

1. Link and image targets `\]\(([^)\s]+)\)`. Skip a target with a scheme (`^[A-Za-z][A-Za-z0-9+.-]*:` or `//`) and a pure anchor.
2. Backticked spans `` `([^`\n]+)` `` that, trimmed, start with `references/` or equal `SKILL.md`.
3. Bare tokens `(?<![\w./-])references/[A-Za-z0-9_\-./]+` in the rest of the line.
4. Normalise: cut at the first `#`; strip trailing `.,;:)`; a trailing `/` marks a folder.
5. Skip placeholders (C5) and the entries of `IGNORED_REFS`.
6. A remaining `references/…` path must be in `tree` (exact case). A folder passes when it exists; it gives an edge to its `README.md` when there is one.

**Rules:**

| Rule id | Fails when |
|---|---|
| `tree-path` | A path from step 6 is not in the tree |
| `tree-relative` | A path is not written from the skill root: a link target (no scheme, not a pure anchor) contains `../` or `./`, starts with `/references/` or is `/SKILL.md`, or ends in `.md` and is not a skill path (a bare `name.md`, or a partial path such as `modes/a.md`); or a backticked span or prose token starts with `/references/` or is `/SKILL.md`. `kiln_skill` refuses a leading `/` (`E_ABS`), and a partial path names no file |
| `tree-bare-name` | A backticked span or prose token equals the base name of a tree file and is not a full path. The dictionary is the base names that are unique in the tree, without `SKILL.md` |
| `tree-call-syntax` | A file contains `skill(name=` or `kiln_skill` |
| `tree-banned-term` | A file contains a term of `BANNED_TERMS` for its scope (table in section 9). The generated files under `references/knowledge/api_docs/` are exempt: their text comes from the API, and a route name may hold such a term |
| `tree-app-link` | Outside `references/docs/` and `api_docs/`: a backticked span or link target matches `^/(specs\|settings\|optimize\|run\|generate\|dataset\|skills\|docs\|prompts\|models\|tools\|fine_tune\|jobs)(/\|\?\|$)` |
| `tree-split-pointer` | In `references/modes/`, `references/levers/` and `references/improving_agents/`: a file matches `held-out\|\b(val\|validation\|test) (split\|set\|gate)\b` and does not contain `references/knowledge/train_val_test.md`. Other files (fine-tuning uses "test split" for a dataset tag) are covered by review |
| `tree-test-split` | Outside `references/docs/` and `references/knowledge/api_docs/`: (a) a line gives `test` as the value of a `split` argument, in the query form `split=test` or the body form `"split": "test"`; or (b) a file other than `references/knowledge/train_val_test.md` contains an entry of `TEST_SPLIT_READERS` (section 9) and does not contain the path `references/knowledge/train_val_test.md`. This is the mechanical part of C13. That no sentence picks, compares or keeps a candidate from a number of the test split is a review rule (batches 9, 13a and 13b) |
| `tree-front-matter` | A file breaks the table in 4.2 |
| `tree-file` | A file is not `.md`, is not UTF-8, contains `\r`, or has a name outside the pattern in section 3 |
| `tree-unreachable` | A file is not reached from `SKILL.md` |

**Allowed exceptions** (the complete list):

- Placeholders (C5).
- `IGNORED_REFS`: `references/STYLE_GUIDE.md` and `references/API_RESPONSE_FORMAT.md` in `references/docs/skills.md` (examples of a user's own skill). Each entry has a comment.
- A bare name as the label of a link whose target is the full path (`docs_index.md` and the help articles use this).
- In a `references/knowledge/api_docs/*_api_list.md` file, a bare `name.md` in the last table column resolves in the same folder. `tree-bare-name` and `tree-banned-term` are off for the whole `api_docs/` folder.
- A base name that is not unique in the tree (`README.md`, `index.md`) is not checked by `tree-bare-name`.

**Reachability.** Breadth-first from `SKILL.md`. Edges: every resolved file path of steps 1–6, folder → `README.md`, catalogue → the endpoint docs of its last column. Each unreached file is one problem; more than 20 in one folder are reported as one line with a count and the first five.

Tests: `test_the_shipped_tree_passes_every_check` and `test_no_rule_is_pending` in `test_shipped_skill.py`; in `test_tree_check.py` one synthetic tree per rule (`test_unresolved_path_fails`, `test_wrong_case_path_fails`, `test_relative_link_fails`, `test_bare_name_fails`, `test_bare_name_in_link_label_passes`, `test_catalogue_bare_name_resolves`, `test_placeholder_is_skipped`, `test_path_in_fence_is_checked`, `test_anchor_and_folder_links_resolve`, `test_call_syntax_fails`, `test_app_path_without_origin_fails`, `test_api_path_is_not_an_app_link`, `test_split_wording_needs_the_pointer`, `test_test_split_request_fails`, `test_test_split_reader_needs_the_pointer`, `test_front_matter_by_type`, `test_unreachable_file_fails`, `test_non_markdown_file_fails`).

## 9. The content port and edit

A large phase (build step 6), run by sub-agents, one batch per pull request. Rules for the phase:

- **Pending rules.** `test_shipped_skill.py` has `PENDING_RULES: set[str]`. A problem of a pending rule does not fail the shipped-tree tests. The phase starts with every tree and knowledge rule pending. Each batch removes the rules it must satisfy. `test_no_rule_is_pending` is enabled in batch 13b.
- **Order.** Batches 1–6 edit the Assistant files, in order. Batch 7 imports the knowledge trees and can run beside 2–6. Batch 8 needs 1 and 7: its lever "See also" lines name Assistant files. Batches 9–12 need both sources. Batch 13a needs 5 and 8–12: it uses the eval job calls of batch 5, the wording of batch 8, `train_val_test.md` (batch 9, which is merged before 13a starts) and `memory.md` (batch 10). Batch 13b needs 13a. Batch 14 is last: it needs the final `SKILL.md`.
- **A path to a file that a later batch writes** is added by that later batch, so that `tree-path` holds after every batch: `train_val_test.md` by batch 9, `code_tool_authoring.md` by batch 11, `run_an_experiment.md` and `diagnose_an_agent.md` by batch 13a.
- **Each sub-agent gets:** its batch row, the file list, the rule for hard cases, the governing rule (C11, section 4.5) and the check to pass. The counts in the table are what the research found, not a quota: a count that differs is reported, not forced.
- **Private-source hygiene (batches 1–6 and 13a).** The export stays outside the repository; no file of it is added, and no committed file names its path. The agent reads each file whole before it writes the ported copy. Nothing comes from the export's service code, policy notes, tool descriptions, manifest or maintenance notes. The copy holds no secret, internal host or URL, person or customer name. The banned terms below catch the known markers. A person reads the diff of batch 1 before merge (functional spec 7.8). Batch 13a reads the three files that are not imported, for the content that 9.2 moves. The same rules apply, and that content is written anew in its destination.

Sources: the Assistant export is 66 files, 548,010 bytes (`SKILL.md`, 4 modes, 26 knowledge files, 34 help articles and their index). 63 of them are imported (520,738 bytes): three knowledge files are not (9.2). The knowledge set is 74 files, 294,116 bytes (7 levers, 30 technique files, 15 smells, 22 playbooks). The API reference exists before this phase.

**Source versions.** The port is made from two fixed versions, and the plan of the content phase records both:

- Harness-tuner at commit `b49f159` (`b49f1594620862876d1e515cdda2f2deff018e95`): the knowledge set, the knowledge tooling and the knowledge backlog (section 7), the `memory` and code-tool-authoring skills (batches 10 and 11), and `gateway/ops.py` as a reference. The model info port (the model info doc) uses the same commit.
- The Assistant export as delivered, built from the `kiln_server` branch of PR 352. It has no commit in this repository, and it stays outside it. A later export will hold the three files of 9.2 again: the plan of the content phase lists them as "not imported", with 9.2 as the reason.

Later fixes from harness-tuner, while two copies of the knowledge exist (functional spec 7.5): diff harness-tuner's knowledge folder (`src/kiln_harness_tuner/agent_files/skills/kiln-harness-tuner-knowledge/`) from the recorded commit to its head; port each change by hand, with the rewrites of batches 7 and 8; run `skill_checks build` and the checks; then update the recorded commit. The recorded commit lives in `.agents/skills/knowledge-maintenance/SKILL.md`, which also holds this procedure. A fix made first in Kiln's copy is not ported back.

Not in this port: the harness-tuner skills `kiln-task-setup` and `experiment-costing`, and the skill-authoring guide. Each is a separate decision (architecture section 8). The role skills and the five role entry files are not ported either (functional spec 7.2). `references/knowledge/run_an_experiment.md` (9.3) is the by-hand form of the build, measure and promote steps that they and harness-tuner's code hold.

**Fixed lists and named outputs.** These are decided here, or are an output of one batch with the rule that decides them:

- *The table of main app pages*: written down in 4.3. *The blocked capabilities and their pages*: written down in 4.4.
- *The size allow-list* of `test_no_file_over_body_limit`: empty. No file of either source, and no generated endpoint doc, is over 30,000 characters today. Rule: a hand-written file over the limit is split, never listed. A generated endpoint doc or a copied help article over the limit may be listed, with a comment that gives the reason.
- *The banned-terms check and generated files*: `tree-banned-term` does not cover `references/knowledge/api_docs/` (section 8).
- *The operation-to-endpoint map* (`OPERATION_ENDPOINTS`): the first output of batch 7, a table in the batch's pull request, one row for each of the 54 gateway operation names: the operation, the REST method and path, and the endpoint doc path or `none`. Rule: an operation maps to the REST endpoint that its handler in harness-tuner's `gateway/ops.py` calls. When the handler calls several, it maps to the one that makes the change, and the lever text names the others in its steps. An operation with no REST call, or whose endpoint is MCP-blocked, maps to `none`. Batch 8 uses the same table for the wording. The table is not kept in the repository.
- *The loop words* (`LOOP_WORDS`): the table below the banned terms. Batch 8 applies it.
- *The test-split readers* (`TEST_SPLIT_READERS`): the first output of batch 9, kept as test data of `tree-test-split` (section 8). One entry for each call and each app page that reads an eval's test split when the caller asks for no split: the endpoint doc path, or the app link. Rule: an entry is added when the endpoint's code, or the request the page makes, resolves the test split with no `split` argument from the caller. The batch checks this in `app/desktop/studio_server/eval_api.py` and in the endpoint docs; it does not go by a name. `train_val_test.md` lists the same entries, each with how to ask for train or val, or with the call to use in its place.
- *The overlap groups* (`OVERLAP_GROUPS`): fixed in 9.1, with the ruling for each group. Batch 13b uses the table for the "See also" lines. It checks the membership against the files as edited, and reports a difference. A group is one subject that both sources teach, with the knowledge documents and the Assistant files that teach it. Rule for membership: an Assistant file is in a group when one of its sections gives advice on when or why to use the thing that a lever, technique, smell or playbook of the group covers. A group whose knowledge side is only a harness-tuner skill that is not ported gets no line.

| # | Batch | What changes (counts from the research) | Rule for hard cases | Verified by |
|---|---|---|---|---|
| 1 | Import the Assistant files; normalise references | Add 63 of the export's 66 files. `experiment_batch.md`, `optimize_quality.md` and `optimize_performance.md` are not imported (9.2). Their 17 inbound references (`improve_task.md` 9, `project_status.md` 3, `create_task.md` 2, `local_private_on_prem.md` 2, `fine_tuning.md` 1) become `references/modes/improve_task.md`; batch 13a refines them. `SKILL.md` gets front matter. 46 `skill(name=…, resource=…)` calls in 19 files become plain paths; 6 bare `skill()` verbs become "read"; the access-rule section goes. 75 bare skill-file names (22 files) and 17 bare API-doc names (7 files) become full paths. Of 7 `../` links in help articles, 6 leave the copied set and become public URLs, and 1 becomes a root path (the import script of C8 does these). The counts of this row and of rows 2, 3 and 5 were made on the 66 files; they drop by what the three files held | 2 `skill()` mentions describe the Kiln product feature and stay. A base name with two matches is fixed by hand | `tree-path`, `tree-relative`, `tree-bare-name`, `tree-call-syntax`, `tree-file`; hygiene review |
| 2 | Model info | About 70 mentions of the three Assistant tools in 13 files (`model_work.md` 21, `improve_task.md` 13, `learn_about_kiln.md` 10) become the model info endpoints through `call_kiln_api`: list and search → `GET /api/model_info/models`, details → `GET /api/model_info/model_details`, providers → `GET /api/model_info/providers`. Rewrite the defining section of `model_work.md`. The model info section of `improve_task.md` is removed, not rewritten: batch 13a rewrites the mode. The 2 mentions in the files that are not imported are gone | "MCP tool" stays only where it means Kiln's tool-server feature (17 hits in 7 files to review) | `tree-banned-term`; `tree-path` for the 3 endpoint docs |
| 3 | Link templates | About 160 app links in 25 files (108 in backticks, 52 link targets, 51 distinct paths) get `http://localhost:8757`; about 11 of them were in the files that are not imported. Rewrite the 4 rule statements, the 10 per-file link tables and the 2 "external URL" definitions | About 6 regex hits are API paths (`/api/…`): leave them | `tree-app-link`; `test_address_replacement_covers_every_app_link` |
| 4 | Identity and on-demand loading | Rewrite `SKILL.md` to 4.3: persona (4 uses of the name), always-in-a-mode, greeting, session start, the compaction rule, the no-repeat-load rules. Rewrite the Session Start and intent-check sections of 3 modes, and `establish_intent.md` | A rule that only makes sense for an always-present system prompt is deleted, not reworded. Rules apply "while you do Kiln work" | `test_skill_md_has_the_required_parts`, `test_skill_md_size`; `tree-banned-term` (scope `SKILL.md`); owner reads `SKILL.md` |
| 5 | UI-only and approval wording | 11 statements in 14 files, against the block list. 19 endpoint docs that the skill names belong to endpoints the Assistant is denied; each is looked up. The agent now does the work for: running an eval, MCP server wiring, RAG setup and indexing, code tools, judges, task from a tool, dataset download. Running an eval is written once, in `specs_and_evals.md`, as the job calls: start, wait, read the errors. The full procedure of an experiment is batch 13a's. The agent still sends the user to the app for every capability of the table in 4.4, which is built from the block list (server doc 6.3) and is not restated here: each gets the C10 wording with the app link of that table. The two "not connected" texts of 4.4 (Kiln Pro, provider) are written in this batch. About 55 approval hits in 20 files: "requires approval" becomes "ask the user first", or goes | The endpoint has a doc in `api_docs/` → write the API workflow. No doc → it is blocked: "ask the user to do this in the app", with the link of 4.4. A blocked capability that 4.4 does not list is reported, and 4.4 gets a row. Product advice (Eval Builder, data-guide jobs) stays as advice. The destructive-action rule stays | `tree-path`; `tree-banned-term` (`UI-only`, `approval-gated`, `requires approval`, `requires user approval`); `test_no_skill_file_names_a_blocked_endpoint`, which lands with this batch |
| 6 | Help-article URLs | A one-off import script (C8; not kept in the repository) adds `online_url` to the 34 articles and removes `<figure>`, `<img>` and Markdown images whose file is not in the tree (79 and 80 tags). `docs_index.md` is regenerated with `skill_checks build`. Other GitBook markup stays | No hand edits except spelling | `tree-front-matter` (every article has its `online_url`); docs index current; `misspell` |
| 7 | Knowledge import and link rewrite | Add 74 files in 4 folders. 367 file-relative links become root paths (levers 18, techniques 168, smells 47, playbooks 134). `gateway_ops` (34 entries, 7 levers) becomes `api_docs`. `detected_by` and `detectors` leave 15 smells. The lever heading is renamed in 7 files. Write the 2 index files and run `build`. The hand-written part of `references/improving_agents/index.md` carries the part "How to read these documents" of the knowledge skill's own `SKILL.md` (the documents are ideas to try; the hard limits; when a clear measurement outranks a document), because the role entry files that lead to it are not ported | First write `OPERATION_ENDPOINTS` (rule above) from harness-tuner's `gateway/ops.py` (reference only; no code is copied). An operation that maps to `none` gets no `api_docs` entry; batch 8 rewords the text. Nothing else in a document changes in this batch (C11) | Every knowledge rule except `size`; `index` current; `tree-relative` |
| 8 | Loop vocabulary | 83 gateway operation names in 12 files (72 in the levers); "gateway" 5; role names 95 in 38 files; "the tuner / the loop / this run" 40 in 25; other harness-tuner skills by name 27 in 13; 1 run-folder path. The loop's own words get the rows of `LOOP_WORDS`: "arm" 173 in 52 files, "val gate" 22 in 20, "probe" 44, "screening round", and the names of loop inputs. Four playbooks name loop inputs in their Situation or their steps, so they have more text to reword, under the same rule: `dealing-with-train-wins-rejected-at-val`, `spending-the-budget`, `dealing-with-a-noisy-eval`, `dealing-with-a-saturated-eval`. Each lever's "See also" loses the names of the skills that are not ported and gets the Assistant files of the table in 4.5. 5 smells get "how to measure this yourself" with the number (prompt over 200,000 characters; tool description over 4,096; skill description over 1,024; more than 40 tools; model older than 8 months). `levers/output_mode.md` and `smells/tools-on-a-live-server.md` are over the size limit after batch 7 and are shortened in their wording; no rule is dropped | C11: vocabulary only. A role becomes "you". An operation becomes its endpoint doc path from `OPERATION_ENDPOINTS`. A loop word becomes its row of `LOOP_WORDS`. A loop-only input becomes what the agent does to get the equivalent; where a general agent cannot get it, the sentence says that the rule applies when running Kiln Harness Tuner. A sentence that only says what loop code does becomes "check it yourself", or goes when it asks nothing of the reader. No rule is deleted, softened, extended or added: a hard limit stays a hard limit. A sentence that cannot be reworded without a change to its rule is reported, not changed. "experiment", "budget", "hypothesis" stay | `tree-banned-term` (scope: the knowledge trees); knowledge `size`, `sections` |
| 9 | Train/val/test | New `references/knowledge/train_val_test.md`. It states harness-tuner's rule, unchanged: tune on train; confirm on val by metrics only; never read test. "Metrics only" is harness-tuner's definition, copied from its source at the pinned commit. The server does not enforce the rule: the agent applies it. The file also has: (a) which call and which app page reads which split, and how to ask for train or val (first write `TEST_SPLIT_READERS`, rule above); (b) what to do when an eval has only a test split: add the train and val splits first, with the user; the agent does not go on with the test split; (c) the leak rules, which the levers state today: no value of a train item in a prompt, a skill or a tool; no copied text of an eval, a judge or a spec; examples use invented values. 79 split mentions in 40 files are reviewed, and the levers name the path for the leak rules | A file may use the words. Only the central file states the rule. Any other statement of the rule is replaced by the path. The file states harness-tuner's rule and nothing weaker or wider (C11): no ruling of its own on per-item pass or fail on val, and none on noise. A case that the source does not cover is reported to the owner, not ruled on | `tree-split-pointer`; `TEST_SPLIT_READERS` lands as test data (`tree-test-split` stays pending until batch 13a); owner reads the file |
| 10 | Memory | New `references/knowledge/memory.md` (at most 12,000 characters) from harness-tuner's `memory` skill (28,273 bytes, 9 gateway mentions): the 6 Memory endpoints with their doc paths, tags, write discipline. Listed in `SKILL.md` and the modes | Run and loop scopes go | `tree-path`, `tree-unreachable`, `tree-banned-term` |
| 11 | Code tools and MCP wiring | Rewrite `code_tools.md`, the wiring part of `tools.md` and of `subagents.md` for the API: read the trust state, ask the user before granting code trust or adding a local MCP server (both run code on the Kiln machine), create, test, iterate. New `code_tool_authoring.md` and 8 files in `code_tool_wrappers/` from harness-tuner's authoring skill (10 files, 46,063 bytes, 16 gateway mentions). The lever `new_tool` gets the path of `code_tool_authoring.md` in its "See also" | Say what a coding agent can do that the Assistant cannot: run the tool's tests | Tree rules; `test_wrapper_templates_compile` |
| 12 | Project files guide | New `references/knowledge/working_with_project_files.md` with the three rules of functional spec 7.4. Listed in `SKILL.md` and 3 modes | It says nothing about val or test data | `tree-unreachable` |
| 13a | The experiment glue and the router | Write `references/knowledge/run_an_experiment.md` and `references/knowledge/diagnose_an_agent.md` (9.3). Rewrite `references/modes/improve_task.md` as the router (9.4). Apply the partial rewrites of 9.2 to 8 knowledge files. Write each piece of unique content of the three files that are not imported in its destination (9.2), and refine the 17 references of batch 1. Each lever's "See also" gets the path of `run_an_experiment.md`. `SKILL.md` part 7 lists `run_an_experiment.md` | C11, C12 and C13. A method statement in an Assistant file is replaced by the path of its owner; it is not reworded into a second statement. Neither glue file holds a rule without a harness-tuner source at the pinned commit; a step with no such source is an API step or a rule for how to talk to the user. Where the by-hand form cannot do what the loop does, the file says that the rule applies when running Kiln Harness Tuner; it puts no weaker rule in its place | `tree-path`, `tree-unreachable`, `tree-split-pointer`, `tree-test-split`; `tree-banned-term` (the three file names); `test_the_glue_files_have_their_parts`; owner reads the two glue files |
| 13b | Wire the knowledge into the Assistant files; final checks | Each Assistant file of a group of 9.1 gets one "See also" line with the full paths of the group's knowledge documents. For the pointer-only files of 9.2 this line and the edit that 9.2 names are the whole change. Check the membership of 9.1 against the files as edited. Then: no pending rule, `misspell`, `checks.sh`, wheel file count | The five-owner rule (C12, section 4.5) decides. A "See also" line gives paths; it states no method. A difference from 9.1 is reported, not forced | `tree-unreachable`; `test_no_rule_is_pending`; all checks |
| 14 | Server and tool texts | Tune the five constants of `texts.py` against the final `SKILL.md`: `SERVER_INSTRUCTIONS`, `SKILL_TOOL_DESCRIPTION`, `PATH_DESCRIPTION`, `CALL_KILN_API_DESCRIPTION`, and `WHAT_KILN_IS` only together with the stub skill text of the install guide. Same terms and the same example path as the skill | The limits win over wording: the first 500 characters of the instructions stand alone, and the whole is under 4,000; the skill description has 100 to 150 words with the trigger rule in the first 500 characters. `PATH_DESCRIPTION` keeps the text of functional spec 6.1 unless the owner agrees to a change | `test_texts.py` and the schema snapshot of `test_server.py` (server doc, section 10); `test_description_is_100_to_150_words_and_front_loaded`; `test_example_paths_exist` |

`BANNED_TERMS` (test data; a term is matched as a whole token):

| Scope | Terms |
|---|---|
| Whole tree | `kiln-chat`, `model_info_featured`, `model_search`, `model_info` (not after `/` or `_`), `compacted_digest`, `UI-only`, `approval-gated`, `requires approval`, `requires user approval`; the names of the three files that are not imported: `experiment_batch`, `optimize_quality`, `optimize_performance` |
| `SKILL.md` | `Kiln Assistant`, `always in context`, `turn 0` |
| Knowledge trees | the 54 operation names of harness-tuner's gateway (names only, from its `gateway/ops.py`), `install_skill_bundle`, `gateway`, `the tuner`, `harness-tuner`, `kiln-harness-tuner`, `the planner`, `the builder`, `the analyzer`, `the probe`, `scratch folder`; the loop's words: `arm`, `arms`, `val gate`, `probe`, `probes`, `screening round`; the loop's inputs and outputs: `open_questions`, `rejected_summary`, `allowed_models`, `model_policy`, `train_noise`, `train_detectability`, `measurement_prices`, `eval_sizes`, `lever_attempts`, `should_wrap_up`, `measure_issue_baseline`, `eval_only`, `eval_building`, `probe_results`, `the planner's skill`, `REJECTED AT VAL` |

The product name, written `Kiln Harness Tuner`, is not a banned term: C11 uses it, and so does `run_an_experiment.md`. The test data must not match it.

`LOOP_WORDS` (batch 8). Each row changes a word, never what a rule requires (C11):

| In the source | In the port |
|---|---|
| arm | candidate, or experiment |
| the val gate | the confirmation on val |
| a probe | a quick check |
| a screening round | a screening |
| the owner (of the agent, or of an eval) | the user |
| `open_questions`, `rejected_summary` | report it to the user |
| "the guidance" | what the user asked |
| `allowed_models`, "the model policy" | the models the user allows; ask the user |
| "code checks …" | "check … yourself" |
| a reason code that code writes (for example the outcome of the confirmation on val) | the outcome in words |
| the noise inputs (`train_noise`, `train_detectability`) | no by-hand equivalent is written. The sentence says that Kiln Harness Tuner measures them and that the rule applies when running it (section 4.5, "Noise") |

**Reviews by people.** They are a phase of their own, build step 9 (architecture section 6), after the content is in place and the error probe is done. They do not gate the batches of this phase. What is reviewed, and what each batch leaves ready for it:

- The sandbox wording (the statement that user code runs with no network or filesystem sandbox, functional spec 15), by a security owner. Batches 5 and 11 touch it; they keep the statement as the source has it and list the two files in the phase notes.
- The public-source claims, by a person: the 19 priors in the knowledge are all marked `Source: public`, and the tree holds no link. Batch 7 lists them in the phase notes. Case studies need a person's approval before they are committed, as before.
- `SKILL.md` (written in batch 4), `train_val_test.md` (batch 9) and the two glue files (batch 13a), read by the owner. The glue files are read against C11: they restate harness-tuner's method by hand and must not change it.

Changes from these reviews are made before the manual sanity check (build step 10).

### 9.1 The overlap groups

The owner approved the merge of the two sources. The deciding rule for every group is the five-owner rule (C12, section 4.5): the playbooks, smells and techniques own when and why; the lever owns how to change something as an experiment; the Assistant file owns how to do it in Kiln; `run_an_experiment.md` owns how to measure, judge and keep; `train_val_test.md` owns the split and leak rules. The governing rule (C11) stands above it: the knowledge's method is ported unchanged.

The research found 11 subjects. This table has 15: it splits "running an improvement loop" in two (the order, and the reading of scores) and adds three (restrictions, fine-tunes, a decision model). Paths are from the skill root: `K/` stands for `references/knowledge/`, `P/`, `T/` and `S/` for `references/improving_agents/playbooks/`, `techniques/` and `smells/`, and `L/` for `references/levers/`.

| # | Subject | Knowledge documents | Assistant files | Ruling |
|---|---|---|---|---|
| 1 | The order of an improvement | `P/know-the-agent-before-you-plan.md`, `P/ordering-work.md`, `P/spending-the-budget.md` | `references/modes/improve_task.md`; not imported: `experiment_batch.md`, `optimize_quality.md` | The knowledge owns the order. The mode is the router. The two files are not imported. `K/diagnose_an_agent.md` has the API steps to read the evidence, and `K/run_an_experiment.md` the by-hand procedure |
| 2 | Measuring and judging a change | `P/dealing-with-a-noisy-eval.md`, `P/dealing-with-train-wins-rejected-at-val.md`, `P/spending-the-budget.md` | `K/eval_scores.md`, `K/benchmark_eval_inputs.md` | The knowledge owns the method: the two stages and the keep rule, unchanged. The paired statistics call of `K/eval_scores.md` is the API procedure that carries it out, on train and on val. `K/run_an_experiment.md` is the one statement of the procedure. No number of the test split is used (C13). The noise playbook is ported as it is |
| 3 | Improving a prompt | `L/prompt.md`; `T/add-the-missing-requirement.md`, `T/one-general-rule-per-edit.md`, `T/structure-a-long-prompt.md`, `T/policy-as-step-by-step-procedures.md`, `T/state-the-output-contract.md`, `T/decline-rules-paragraph.md`, `T/prune-one-group-at-a-time.md`; `S/very-long-prompt.md`; `P/requirement-missing-from-the-prompt.md`, `P/lost-in-long-instructions.md`, `P/wrong-scope-or-refusal.md`, `P/change-the-surface-not-the-words.md` | `K/prompt_audit.md`, `K/prompt_rewrite.md` | The knowledge owns when and what to change. `K/prompt_audit.md` is a review checklist, not a first step. An experiment makes a new saved prompt and a new run config, never an edit in place. `K/prompt_rewrite.md` keeps the API steps |
| 4 | Model choice | `L/model.md`; `T/model-swap-inside-a-class.md`, `T/faster-provider-for-the-same-model.md`; `S/old-model.md`; `P/dealing-with-an-eval-near-zero.md` | `K/model_work.md` | The knowledge owns when to swap. The Assistant file owns the model facts, the provider checks and the price arithmetic for a question that is not about a task |
| 5 | Run parameters | `L/params.md`; `T/thinking-level-ladder.md` | `K/model_create_configs.md` ("Key Parameters") | The knowledge owns it. The section becomes a field list with the lever paths |
| 6 | Structured output mode | `L/output_mode.md`; `P/output-contract-not-met.md`; `T/state-the-output-contract.md` | `K/model_create_configs.md` | The knowledge owns it. The Assistant file names the field and the lever path |
| 7 | Cheaper or faster as a goal | `P/cheaper-or-faster.md` and the techniques it links | `K/model_work.md` ("Proportion Recommendations"); not imported: `optimize_performance.md` | The knowledge owns it. The file is not imported. Its reporting rules move to `K/model_work.md` |
| 8 | An eval that is itself the problem | `P/dealing-with-a-wrong-eval.md`, `P/dealing-with-a-saturated-eval.md`, `P/dealing-with-a-noisy-eval.md`, `P/dealing-with-an-eval-near-zero.md` | `K/specs_and_evals.md`, `K/create_spec.md`, `K/judge_types.md`, `K/eval_scores.md` | The knowledge owns when the eval is the problem and what not to do, unchanged. The Assistant files own how to create or change an eval or a judge in Kiln. "The owner" of the knowledge is the user (`LOOP_WORDS`) |
| 9 | Skills | `L/skill.md`; `T/long-prompt-into-a-skill.md`, `T/document-into-a-skill.md`, `T/guide-skill-for-a-tool-set.md`, `T/rewrite-an-inherited-skill.md`, `T/skill-into-the-prompt.md`; `S/one-file-skill-with-many-topics.md`, `S/skill-too-small-to-earn-its-place.md`, `S/very-long-skill-description.md`, `S/faulty-inherited-skill.md`; `P/skill-is-not-read.md` | `K/adding_skills.md` | The knowledge owns when to use a skill and the shape of a skill. The Assistant file keeps the endpoints and the name limits |
| 10 | Tools and code tools | `L/tool_config.md`, `L/new_tool.md`; `P/fit-the-tool-layer-to-the-agent.md`, `P/wrong-tool-chosen.md`, `P/failure-at-a-tool-call.md`, `P/malformed-tool-calls.md`, `P/missing-context-the-agent-could-be-given.md`; the tool techniques; the tool smells | `K/tools.md`, `K/code_tools.md`, `K/code_tool_authoring.md`, `K/subagents.md` | No opposite advice. The Assistant files own the setup. The knowledge owns the design. `K/subagents.md` has no knowledge document |
| 11 | Grounding and RAG | `P/answers-not-grounded.md`; `T/attach-the-knowledge-source.md`, `T/answer-only-from-the-source.md`, `T/document-into-a-skill.md`; `S/document-behind-a-lookup-tool.md` | `K/rag.md` | The knowledge owns the order of work. The Assistant file owns the setup |
| 12 | Creating a task and a run config | Every lever ("Rules of the object") | `K/create_task.md`, `K/model_create_configs.md` | The Assistant files own it. Each lever's "See also" names them. For an experiment, the lever's rule applies: copy the parent, change one thing |
| 13 | Restrictions, local and private models | `P/working-inside-restrictions.md` | `K/local_private_on_prem.md` | No opposite advice. The playbook's rules stand as they are. The Assistant file owns the model facts and the setup |
| 14 | Fine-tunes | `T/model-swap-inside-a-class.md` (How, step 6); `L/model.md` (Limits) | `K/fine_tuning.md` | The Assistant file owns how. Its list of what to try first becomes the path of `P/ordering-work.md` |
| 15 | A classifier on a decision model | `T/decision-model-for-a-classifier.md` | `K/typesafe_jev.md` | No opposite advice. The technique says when. The Assistant file says how |

By the membership rule, cost estimation gets no line of its own: its knowledge side beyond `P/spending-the-budget.md` is the skill `experiment-costing`, which is not ported. The part "Cost before you spend" of `K/run_an_experiment.md` names what it takes from that skill.

### 9.2 The Assistant's files, one by one

The export has 31 hand-written files (`SKILL.md`, 4 modes, 26 knowledge files). The merge deletes 3, rewrites 9 in part (the mode and 8 knowledge files) and gives 12 a pointer or one small edit. The rest are not touched by the merge. Batch 1 does the first group; batch 13a the second; batch 13b the third, except where a row names another batch.

**Not imported (3).** Each is a method document on a subject that the knowledge owns. Each piece of content that only the file has gets a destination:

| File | Content that only this file has | Destination |
|---|---|---|
| `experiment_batch.md` | What must exist before an experiment, and the order spec → judge → run → compare | `run_an_experiment.md`, "Before you start" |
| | Ask the user before 3 or more run configs are created | `run_an_experiment.md`, "Variants" (it is also in `model_work.md`) |
| | The form of the Compare link, and its limit of 6 run configs | Already in `eval_scores.md`. It stays there, with the split that the page reads (C13) |
| | What to do next, by outcome | `run_an_experiment.md`, "Keep or discard", as paths of playbooks |
| | Its table of endpoints | `run_an_experiment.md` |
| `optimize_quality.md` | The map from a kind of problem to a starting point | The routing table of `improve_task.md` (9.4) |
| | The map from a problem to a type of eval | `create_spec.md` |
| | The list of prompt layers to review | `prompt_audit.md`, as checklist items |
| | The scorecard of where the task stands today | `diagnose_an_agent.md`, "The scores on train" |
| | Ask before an eval is built during another request | One line in `improve_task.md` |
| `optimize_performance.md` | Lead with a recommendation that holds quality; the cost multipliers | `model_work.md`, "Proportion Recommendations" |
| | State no latency number that no call returned | `model_work.md`, the model info section |
| | The call that returns the rendered prompt | `diagnose_an_agent.md`, "What the smells measure" |
| | Measured cost from the stored usage | Already in `eval_scores.md` |

The rest of the three files is method on subjects that the knowledge owns (the order of work, what one experiment changes, the steps towards a cheaper or faster agent, prompt length, the output mode). It is not carried over: the routing table of 9.4 names the playbook for each.

**Rewritten in part (9).** In each, the API steps stay and a method section becomes the path of its owner:

| File | Stays | Changes |
|---|---|---|
| `references/modes/improve_task.md` | Task context discovery, the snapshot call, the questions to the user, the links | Becomes the router into the knowledge (9.4) |
| `prompt_audit.md` | The review checklist | It is a checklist for two uses: a new prompt (`create_task.md` reads it) and a user who asks for a review. It is not a first step of an improvement. Each group of the checklist names the knowledge document for that problem; a statement that the knowledge makes is replaced by the path. Reasoning points to the lever `params`; examples point to the leak rules of `train_val_test.md` |
| `prompt_rewrite.md` | Reading the prompt, creating a saved prompt, the prompt types, the notes on the app pages | The sections on what to change and how to propose it become the paths of the lever `prompt` and of `run_an_experiment.md`. The edit in place of a task instruction or a saved prompt moves under a heading for project operations, with the immutability rule of `working_with_project_files.md`. The call that builds a prompt from dataset examples names the leak rules of `train_val_test.md` |
| `model_work.md` | The model info section (batch 2), the shared rules, the tiers, the providers, the sizing of open-weight models, the workflows A and C | Workflow B keeps its first step (map what exists). For when a swap is a good experiment it names `T/model-swap-inside-a-class.md`; for a comparison that the user asks for it names `run_an_experiment.md`, "Variants". Cost estimation keeps the price arithmetic for a question that is not about a task, and names `run_an_experiment.md` for an eval run. It says that a tier is the "class" of the knowledge. It receives the two pieces of `optimize_performance.md` |
| `model_create_configs.md` | Everything on the API: the URL note, the check of the model and provider pair, the name rules, the prompt id, the create call | "Key Parameters" becomes a list of the fields, one line each, with the path of the lever (`params`, `output_mode`, `tool_config`). Above the create call, one line names the lever's rule for an experiment: copy every property of the parent and change one |
| `eval_scores.md` | The paired statistics recipe, the reporting rules, the two paths for a task with no scores yet (the eval is now started through the API, batch 5) | Every score call is listed with the split it reads and with how to ask for train or val (C13). The recipe is pointed at train and val, as `run_an_experiment.md` uses it. One pointer per eval problem to its playbook |
| `specs_and_evals.md` | What evals are, the kinds of judges, the design principles (batch 5 rewrites the agent's role and running an eval) | The table of splits names `train_val_test.md` for the use of train and val in an experiment. Pointers to the five eval playbooks |
| `benchmark_eval_inputs.md` | How to recognise the eval, the two item types, the reference data, shared generation, which score call to use | The steps of its recipe that measure and compare become the path of `run_an_experiment.md` |
| `adding_skills.md` | The endpoints, the name limits, the immutability note | "When to use a skill" becomes pointers to the techniques. The authoring advice names the lever `skill` and the skill smells for the shape of a skill. The attach step is checked against the endpoint doc (open item) |

**A pointer or one small edit (12).**

| File | Edit |
|---|---|
| `tools.md`, `subagents.md`, `rag.md` | One "See also" line each. `tools.md` names the two smells on the size of the tool set and does not repeat their numbers |
| `code_tools.md` | As batch 11, plus the path of the lever `new_tool` |
| `fine_tuning.md` | Its list of what to try first becomes the path of `P/ordering-work.md`. The comparison after a fine-tune names `run_an_experiment.md` |
| `local_private_on_prem.md` | Its experiment section names `P/working-inside-restrictions.md`, `T/model-swap-inside-a-class.md` and `run_an_experiment.md` |
| `typesafe_jev.md`, `create_spec.md`, `judge_types.md` | One "See also" line each: the decision-model technique; the playbooks for a wrong eval and for a saturated eval. `create_spec.md` also receives the map from a problem to a type of eval |
| `project_status.md`, `create_task.md`, `freeform_help.md` | Their references to the three files that are not imported name `references/modes/improve_task.md` |

### 9.3 The two glue files

Neither source has them. Both are hand-written knowledge files with the front matter of 4.2, and both follow C11: they add no rule, and they change none.

**`references/knowledge/run_an_experiment.md`** (about 10,000 characters). The owner of "how to measure a change, judge it and keep it" (C12).

It opens by offering two paths and telling the agent how to choose. This opening is the owner's ruling:

- **Kiln Harness Tuner**: for experimentation at scale, which is many waves of experiments, managed automatically. It is Kiln's best method. It takes a while and can use many tokens. An agent that is in a chat with a user still dispatches this work to Harness Tuner. It never takes over the management of many-wave, complex experimentation itself.
- **A one-off**: the user wants to try one or two clear ideas. The agent does this in the chat, with the by-hand procedure of this file, and does not start Harness Tuner.

The rest of the file is the by-hand procedure for the one-off path. Until the knowledge file `using_harness_tuner` exists (the first new entry of the backlog, section 7), the Harness Tuner path tells the agent to recommend Harness Tuner to the user. It gives no CLI steps.

| # | Part | Content | Source of the method (harness-tuner) | Source of the Kiln steps (Assistant file) |
|---|---|---|---|---|
| 1 | Two paths | As above | The owner's ruling | — |
| 2 | Words | Baseline (the parent), candidate, target eval, guard eval | The knowledge skill's `SKILL.md`, "The parts" | — |
| 3 | Before you start | An eval with a default judge measures the problem. It has a train and a val split; when it has only a test split, the splits are added first (`train_val_test.md`) and the procedure does not go on with the test split. The baseline run config is known. The user gave the goal, the restrictions, the models allowed and a spend limit | `P/know-the-agent-before-you-plan.md`; harness-tuner's guide for a user's own task | `experiment_batch.md` (not imported); `specs_and_evals.md` |
| 4 | The hypothesis | One change. The failure it fixes. The target eval. The predicted effect, which is not larger than the room the baseline leaves on train | `P/spending-the-budget.md`; `P/dealing-with-a-noisy-eval.md`; the batch-selection role skill | — |
| 5 | Cost before you spend | Run the eval on a small sample of train items, read the recorded usage, and scale it to the number of items and evals. Count the judge and, for a multi-turn eval, the synthetic user. Tell the user. Ask when it is above the limit | `P/spending-the-budget.md`; the skill `experiment-costing` (not ported): read the recorded usage, never scale a list price | The eval job call with an item list; `model_work.md` |
| 6 | Build the candidate | New objects only. Copy every property of the parent and change one. The hypothesis goes in the name and the description of the run config. Then check that the change took effect, with the check that the technique gives. A change that did not reach the agent is not measured | Each lever ("Rules of the object"); each technique ("Check that it took effect"); the experiment-build role skill | `model_create_configs.md`; `prompt_rewrite.md`; the run call |
| 7 | Measure on train, and judge | First the leak rules of `train_val_test.md`. Start the eval job on the train split, the target eval first. Wait. Read the job errors and the coverage. Compare with the baseline per item, with the paired statistics call. Read the failing items. Give the verdict as harness-tuner states it: candidate, refuted, inconclusive or not applied | The experiment-analysis role skill; the planner's entry file (the four outcomes); the limits of the levers | The eval job calls; `eval_scores.md` (the paired recipe, the coverage rule) |
| 8 | Confirm on val | Run the evals on val for the candidate and the baseline. Read the result by metrics only, as `train_val_test.md` defines it. Apply the keep rule as harness-tuner's promote step states it: the target eval clearly better, no eval clearly worse, higher priorities before lower ones, cost and latency as a separate axis, one winner or none. Confirm a candidate once. Do not tune on val. The user may waive this step; the report is then marked "train only" | The promote role skill; the batch-selection role skill (the rule for a cost or speed goal); `P/dealing-with-train-wins-rejected-at-val.md` | `eval_scores.md` (the paired statistics call, on val); `train_val_test.md` |
| 9 | Keep or discard | Keep: the candidate is the baseline of the next experiment. The procedure never changes the task's default run config. Discard: the objects stay; they are history. Then, by outcome, the playbook to read next | The promote role skill (its hard rules); the planner's entry file | `experiment_batch.md` (not imported) |
| 10 | Record and report | One record per experiment: hypothesis, ids, train result, val result, verdict, next step (`references/knowledge/memory.md`). To the user: the recommendation first, a table with coverage and significance, the split that each number came from, the links. No number of the test split | The experiment-analysis role skill (what it returns); the `memory` skill | `eval_scores.md` (the reporting rules) |
| 11 | Variants | A comparison of run configs that the user named: the same train items for each, then parts 7 and 8 for the best one; ask before 3 or more run configs are created. Two candidates at once: each is one change from the same parent, and two winners together are a new candidate, measured as one. No eval yet: an eval comes first (`create_spec.md`). More than this is the Harness Tuner path of part 1 | The batch-selection role skill; `P/cheaper-or-faster.md`; the experiment-build role skill (merging) | `experiment_batch.md` (not imported); `model_work.md`; `create_spec.md` |

The file has no part on noise and none on per-item pass or fail on val: it names `P/dealing-with-a-noisy-eval.md` and `train_val_test.md` (section 4.5). On val, the paired statistics call is used inside harness-tuner's definition of "metrics only". If the call needs more than that definition allows, batch 13a reports it to the owner and does not decide (open item).

**`references/knowledge/diagnose_an_agent.md`** (about 5,000 characters). It is limited to the Kiln API steps that read what the knowledge already tells the agent to look at: the agent as it is, its outputs and its traces. It adds no method: what to look for, how to name a failure and what to do about it are in the smells and the playbooks. It reads train items only, and names `train_val_test.md`.

| # | Part | The Kiln API steps for | The knowledge that asks for it | Source of the steps (Assistant file) |
|---|---|---|---|---|
| 1 | The agent as it is | The task, the baseline run config with its frozen prompt, its tools and skills, the evals and their default judges | `P/know-the-agent-before-you-plan.md`; each lever ("What it is") | `improve_task.md` (the snapshot call); `prompt_audit.md` (reading the task and the prompt); `tools.md` (the tool state) |
| 2 | What the smells measure | The rendered prompt and its length, the tool and skill descriptions, the number of tools, the release date of the model | The smells that batch 8 gave a number to measure | `optimize_performance.md` (not imported: the rendered-prompt call); the model info endpoints |
| 3 | The scores on train | The per-item results of each eval on the train split, for the baseline | `P/ordering-work.md`; the eval playbooks | `eval_scores.md`; `optimize_quality.md` (not imported: the scorecard) |
| 4 | The failing train items | For each: the output, the expected output, the judge's reasoning and the trace. For a multi-turn eval: the reference data and the driven conversation | The failure playbooks | The results call; `project_status.md` (one run and its trace); `benchmark_eval_inputs.md` |
| 5 | Where to go next | No steps: the path of `references/improving_agents/index.md` | — | — |

### 9.4 The router: `references/modes/improve_task.md`

About 8,000 characters. The mode states no method of its own (C12). Its parts, in order:

1. **The goal and the owners.** One line for each owner of 4.5, with its path.
2. **The two paths**, in two lines, with the path of `references/knowledge/run_an_experiment.md`: experimentation at scale is dispatched to Kiln Harness Tuner, and the agent never manages it itself; one or two clear ideas are done in the chat with the by-hand procedure.
3. **Task context.** Task context discovery and the snapshot call stay as they are. So do the questions to the user at the start: the goal, the restrictions, the models allowed, a spend limit.
4. **The usual path for a one-off**, with one path per step: `references/knowledge/diagnose_an_agent.md` → the playbook, through `references/improving_agents/index.md` → `references/knowledge/run_an_experiment.md`. Inside the knowledge the path is smell or playbook → technique → lever. Prefer a playbook.
5. **A routing table by what the user asks.** It replaces the mode's fixed map from an intent to a set of files.

   | The user asks | Start from |
   |---|---|
   | Make it better; fix a named problem | `diagnose_an_agent.md`, then the failure playbook that fits |
   | Many rounds of experiments; take it as far as it goes | The Harness Tuner path of `run_an_experiment.md` |
   | Cheaper or faster | `P/cheaper-or-faster.md`, with `model_work.md` |
   | Which model is best; compare these run configs | `run_an_experiment.md` ("Variants"), with `model_work.md` and `T/model-swap-inside-a-class.md` |
   | The scores jump, all pass, none pass, the judge looks wrong | The eval playbook that fits, then `judge_types.md` or `create_spec.md` for the change |
   | A provider, origin or privacy limit; a local model | `P/working-inside-restrictions.md`, `local_private_on_prem.md` |
   | Add a tool, a skill, retrieval, a sub-agent | The Assistant file for the setup, the lever, and the technique or smell that says when it helps |
   | Fine-tune | `fine_tuning.md`, after `P/ordering-work.md` |
   | How did my evals go | `eval_scores.md` |
   | Add an eval; choose a judge | `create_spec.md`, `specs_and_evals.md`, `judge_types.md` |
   | There is no eval yet | An eval first: `create_spec.md` |

6. **Reporting.** The recommendation first, then the evidence with the split of each number, then the links. One line: a help article says what a feature does; the knowledge says when to use it.
7. **The knowledge table**, in four groups. *Method*: `references/improving_agents/index.md`, `references/levers/index.md`, `diagnose_an_agent.md`, `run_an_experiment.md`, `train_val_test.md`, `memory.md`. *Run configs, models, prompts*: `model_work.md`, `model_create_configs.md`, `prompt_rewrite.md`, `prompt_audit.md`, `fine_tuning.md`, `local_private_on_prem.md`, `typesafe_jev.md`. *Evals*: `eval_scores.md`, `specs_and_evals.md`, `create_spec.md`, `judge_types.md`, `benchmark_eval_inputs.md`, `data_guides.md`. *Capabilities*: `tools.md`, `code_tools.md`, `code_tool_authoring.md`, `subagents.md`, `adding_skills.md`, `rag.md`.

The file names in this section are short for readability. In the skill every one is a full path (C1). Gone from the mode: the fixed map from an intent to files, the model info section (batch 2), and the intent check and session start (batch 4).

## 10. Test plan

The "Step" column is the build step of architecture section 6 in which the tests land. The tests of `skill_files` and `skill_tool` build a small synthetic tree in `tmp_path` and pass it to `build_index`, so they do not depend on the shipped content; the tests that read the shipped tree are in `test_shipped_skill.py`.

| File | Step | Tests |
|---|---|---|
| `test_skill_files.py` | 1 | `test_index_holds_skill_md_and_posix_keys`; `test_index_without_skill_md_raises`; `test_index_skips_hidden_and_pycache`; `test_resolve_path` (parametrised: every row of the table in 2.4); `test_each_error_text` (exact strings of 2.5); `test_not_found_lists_nearest_folder`; `test_not_found_lists_sub_folders`; `test_not_found_suggests_case_fix`; `test_folder_path_is_an_error`; `test_api_docs_listing_is_short`; `test_raw_is_cleaned_and_cut`; `test_strip_front_matter` (present, absent, unclosed); `test_reference_file_keeps_front_matter`; `test_apply_origin_only_when_different`; `test_read_is_byte_exact`. The cases of `app_origin` are in the server doc's `test_addresses.py` |
| `test_skill_tool.py` (through a FastMCP client session) | 1 | `test_schema_has_only_optional_path` (one property, no `required` key); `test_meta_always_load`; `test_no_args_returns_skill_md_without_front_matter`; `test_path_returns_file_text`; `test_resource_alias`; `test_stray_name_skill_id_ignored`; `test_error_is_iserror_without_sdk_prefix`; `test_no_structured_content`; `test_non_default_origin_is_replaced` (registered with port 9000); `test_host_header_is_not_used` (a request with `Host: example.test:1234` gets the address of the bound host and port); `test_wrong_type_is_an_error`; `test_description_is_100_to_150_words_and_front_loaded` |
| `skill_checks/test_tree_check.py` | 4 | Section 8 |
| `skill_checks/test_api_reference.py` | 4 | `test_drop_blocked_removes_operations_and_empty_paths`; `test_other_method_stops`; `test_version_is_normalised`; `test_catalogue_index_rows`; `test_write_folder_replaces_whole_folder`; `test_diff_folder_reports_added_removed_changed`; `test_collision_warning_stops` (fake generator) |
| `app/desktop/test_skill_api_reference.py` | 4; the last test in batch 5 of step 6 | `test_the_committed_api_reference_is_current` (skips below 3.13; `slow`); `test_committed_docs_match_the_block_list` (all versions); `test_no_skill_file_names_a_blocked_endpoint` (below) |
| `skill_checks/test_knowledge_check.py` | 5 | Section 7 |
| `skill_checks/test_knowledge_backlog.py` | 5 | The format tests of `app/mcp/knowledge_backlog.md`, ported from harness-tuner's `tests/test_backlog.py`, with the `Kind` and `Where` values of section 7: the real file has no problem of any rule; one small text per rule, each with one deliberate violation. `test_the_backlog_is_outside_the_package` (the file is not under `kiln_mcp_server/`) |
| `skill_checks/test_shipped_skill.py` | 4, 5, then per batch in 6 | Step 4: `test_the_shipped_tree_passes_every_check` (with `PENDING_RULES`), `test_the_catalogue_index_exists` (`skill_files.API_CATALOGUE_INDEX_PATH` is a file of the tree), `test_no_file_over_body_limit` (each file at most 30,000 characters; the allow-list of section 9). Step 5: `test_the_shipped_knowledge_passes_every_check`, `test_each_template_gives_a_valid_document`, `test_the_maintenance_skill_names_the_commands`. Step 6, with the batch that makes each pass: `test_docs_index_is_current` (batch 6), `test_the_generated_blocks_are_current` and `test_a_document_of_each_type_exists` (batch 7), `test_example_paths_exist` (the paths in `SKILL_TOOL_DESCRIPTION`, `PATH_DESCRIPTION` and `HINT`; batch 1), `test_address_replacement_covers_every_app_link` (no file holds `127.0.0.1:8757`, `https://localhost:8757`, or `localhost:8757` without `http://`: forms the replacement would miss; batch 3), `test_skill_md_has_the_required_parts` and `test_skill_md_size` (batch 4), `test_wrapper_templates_compile` (batch 11), `test_the_glue_files_have_their_parts` (batch 13a: `run_an_experiment.md` has the parts of 9.3 in order, and its first part names Kiln Harness Tuner and the one-off path; `diagnose_an_agent.md` has its parts), `test_no_rule_is_pending` (batch 13b) |

`test_no_skill_file_names_a_blocked_endpoint` (C10). It needs the app, so it is in `app/desktop`. It reads the blocked operations from `make_app().routes` with `is_mcp_denied`, and turns each path template into a pattern in which a `{param}` matches `{…}` or one path segment, and which must not be followed by another path character. It searches every file of the shipped tree outside `references/knowledge/api_docs/`. A hit fails when every method of that path is blocked. When the path also has an allowed method (today only `/api/settings`: `GET` allowed, `POST` blocked), a hit fails only when the blocked method is on the same line. The generated reference already has no blocked endpoint (`test_committed_docs_match_the_block_list`).

The bundling test (collected data against the file index) is the server doc's, in `app/desktop/test_pyinstaller_hooks.py`; this doc has no copy of it. No test reaches the network. The manual checks of functional spec 16 exercise the content.

## Open items

To verify during implementation:

- **The generator pin** inside the real workspace (it was tested in a throwaway project), in build step 4.
- **The knowledge tooling on Python 3.10** (the source was read, not run there), and `ty` and ruff on the ported code, in step 5.
- **Help-article URLs.** The 34 `online_url` values come from the public sitemap; no URL was requested directly. Request each one in batch 6.
- **Attaching a skill to a run config** (batch 5): the Assistant text says the API cannot do it. Check against the generated endpoint doc.
- **`misspell`** over the ported text (batches 6 and 13b).
- **The source of "metrics only"** (batch 9): find harness-tuner's definition at the pinned commit and copy it; the pull request names the file it came from. If the paired statistics call on val (9.3, part 8) needs more than the definition allows, report it to the owner. The batch does not decide.
- **`TEST_SPLIT_READERS`** (batch 9): check each score call and the Compare page against the code and the endpoint docs, and note for each whether it takes a `split` argument.
- **Adding a train or a val split to an eval that has only a test split** (batch 9): which endpoint does it, and whether it is allowed over MCP. If it is not, the C10 wording with the app page.
- **Project files and the split rule.** Functional spec 7.4 says that the project files guide says nothing about val or test data, and batch 12 follows it. The merge proposal asked for a line there that names `train_val_test.md`. It is not applied: it needs a change to the functional spec, which is the owner's.
- **The backlog groups** (build step 5): the owner reads the three lists of section 7 (come over, stay behind, dropped), with the 8 `tuner`-only gap entries in view.
- **One improvement, start to finish**, in the manual sanity phase: a one-off with the by-hand procedure, and a request for experimentation at scale, which must end in a recommendation of Kiln Harness Tuner.
- **`alwaysLoad`**: whether it holds in every Claude Code configuration. Manual sanity phase.

Owner decisions are in [architecture.md](../architecture.md) section 11: the merge of the two sources is approved, with the knowledge's method ported unchanged (item 1; sections 4.5 and 9.1 to 9.4 here); the knowledge backlog is ported to `app/mcp/knowledge_backlog.md` (item 2; section 7 here). The reviews by people (the sandbox wording, the public-source claims, case studies, the owner's read of `SKILL.md` and `train_val_test.md`) are build step 9, after the content is in place. Follow-ups (the help-article refresh, the harness-tuner skills that are not ported, the knowledge file `using_harness_tuner`) are in architecture section 8.
