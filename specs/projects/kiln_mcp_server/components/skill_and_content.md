---
status: draft
---

# Component: Skill and content

Covers the `kiln_skill` tool, the skill tree and its packaging, the API reference pipeline, the knowledge tooling, the skill-tree check, and the content port. Spec sections: [functional_spec.md](../functional_spec.md) 6, 7, 16. The server, the PyInstaller hook with its test, and the module `texts.py` are in [mcp_server_and_api_tool](mcp_server_and_api_tool.md) (the server doc below). The MCP block list is section 6 of that doc. Cross-cutting decisions, shared files and the build order are in [architecture.md](../architecture.md).

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
    api_reference.py        render / write / diff of api_docs from a spec dict (section 6).
                            It never imports app.desktop; the spec is built in app/desktop.
  test_*.py                 beside each module
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
                                        working_with_project_files.md, code_tool_authoring.md
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

### 4.1 Conventions (C1–C7 have a check in section 8; C10 has a test in section 10; C8 and C9 are review rules, with the checks they name)

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
5. Confirm with the user before a destructive or irreversible operation.
6. Links into the app: the C4 rule and the table of main pages below.
7. Map of the other entry points, one line each: `references/docs/docs_index.md`, `references/levers/index.md`, `references/improving_agents/index.md`, `references/knowledge/train_val_test.md`, `references/knowledge/memory.md`, `references/knowledge/working_with_project_files.md`, `references/knowledge/model_work.md`.
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
5. `run_generator`: run `[sys.executable, "-m", "openapi2skill", "--spec", <file>, "--output", <tmp>/out]` with `PYTHONUTF8=1`. Stop on a non-zero exit, or on a stderr line that starts with `Warning: filename collision`. The output folder is the single child of `<tmp>/out` (its name is a timestamp). Read every file of its `reference/` folder; decode UTF-8; turn `\r\n` into `\n`. Ignore the generator's own `SKILL.md`. File names are kept as generated. Stop when the count of endpoint docs differs from the count of operations in the spec.
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

**As pytest** (in `skill_checks/`): `test_knowledge_check.py` ports `tests/test_knowledge_checks.py` (one synthetic tree per rule through `build_tree`, new paths, the three removed rules deleted, `lever-api-docs` added). `test_shipped_skill.py` holds `test_the_shipped_knowledge_passes_every_check`, `test_the_generated_blocks_are_current`, `test_a_document_of_each_type_exists`, `test_each_template_gives_a_valid_document` and `test_the_maintenance_skill_names_the_commands`. The tests tied to roles, agent CLIs, batch plans and detectors stay in harness-tuner.

**`knowledge-maintenance` skill.** Moves to `.agents/skills/knowledge-maintenance/` with `templates/`. Edits: paths and commands; who reads the knowledge (any agent on the Kiln MCP); "nothing from the target" becomes "nothing measured on a user's project or on a demo project"; the schema part of harness-tuner's design document becomes `references/schema.md` inside the skill; the language rule covers the two knowledge trees only; the backlog procedure is removed, because harness-tuner's `specs/backlog.md` is not ported (where the backlog lives afterwards is architecture section 11, item 2). Section 8 of the harness-tuner skill moves unchanged: **a person approves a case study or a prior before it is committed, unless it is clearly public, with its link.** `AGENTS.md` gets one line that names the skill and this rule.

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
| `tree-relative` | A link target contains `../` or `./`, or is a bare `name.md` |
| `tree-bare-name` | A backticked span or prose token equals the base name of a tree file and is not a full path. The dictionary is the base names that are unique in the tree, without `SKILL.md` |
| `tree-call-syntax` | A file contains `skill(name=` or `kiln_skill` |
| `tree-banned-term` | A file contains a term of `BANNED_TERMS` for its scope (table in section 9). The generated files under `references/knowledge/api_docs/` are exempt: their text comes from the API, and a route name may hold such a term |
| `tree-app-link` | Outside `references/docs/` and `api_docs/`: a backticked span or link target matches `^/(specs\|settings\|optimize\|run\|generate\|dataset\|skills\|docs\|prompts\|models\|tools\|fine_tune\|jobs)(/\|\?\|$)` |
| `tree-split-pointer` | In `references/modes/`, `references/levers/` and `references/improving_agents/`: a file matches `held-out\|\b(val\|validation\|test) (split\|set\|gate)\b` and does not contain `references/knowledge/train_val_test.md`. Other files (fine-tuning uses "test split" for a dataset tag) are covered by review |
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

Tests: `test_the_shipped_tree_passes_every_check` and `test_no_rule_is_pending` in `test_shipped_skill.py`; in `test_tree_check.py` one synthetic tree per rule (`test_unresolved_path_fails`, `test_wrong_case_path_fails`, `test_relative_link_fails`, `test_bare_name_fails`, `test_bare_name_in_link_label_passes`, `test_catalogue_bare_name_resolves`, `test_placeholder_is_skipped`, `test_path_in_fence_is_checked`, `test_anchor_and_folder_links_resolve`, `test_call_syntax_fails`, `test_app_path_without_origin_fails`, `test_api_path_is_not_an_app_link`, `test_split_wording_needs_the_pointer`, `test_front_matter_by_type`, `test_unreachable_file_fails`, `test_non_markdown_file_fails`).

## 9. The content port and edit

A large phase (build step 6), run by sub-agents, one batch per pull request. Rules for the phase:

- **Pending rules.** `test_shipped_skill.py` has `PENDING_RULES: set[str]`. A problem of a pending rule does not fail the shipped-tree tests. The phase starts with every tree and knowledge rule pending. Each batch removes the rules it must satisfy. `test_no_rule_is_pending` is enabled in batch 13.
- **Order.** Batches 1–6 edit the Assistant files, in order. Batches 7–8 edit the knowledge trees and can run beside 2–6. Batches 9–13 need both. Batch 14 is last: it needs the final `SKILL.md`.
- **Each sub-agent gets:** its batch row, the file list, the rule for hard cases, and the check to pass. The counts in the table are what the research found, not a quota: a count that differs is reported, not forced.
- **Private-source hygiene (batches 1–6).** The export stays outside the repository; no file of it is added, and no committed file names its path. The agent reads each file whole before it writes the ported copy. Nothing comes from the export's service code, policy notes, tool descriptions, manifest or maintenance notes. The copy holds no secret, internal host or URL, person or customer name. The banned terms below catch the known markers. A person reads the diff of batch 1 before merge (functional spec 7.8).

Sources: the Assistant tree is 66 files, 548,010 bytes (`SKILL.md`, 4 modes, 26 knowledge files, 34 help articles and their index). The knowledge set is 74 files, 294,116 bytes (7 levers, 30 technique files, 15 smells, 22 playbooks). The API reference exists before this phase.

**Source versions.** The port is made from two fixed versions, and the plan of the content phase records both:

- Harness-tuner at commit `b49f159` (`b49f1594620862876d1e515cdda2f2deff018e95`): the knowledge set, the knowledge tooling (section 7), the `memory` and code-tool-authoring skills (batches 10 and 11), and `gateway/ops.py` as a reference. The model info port (the model info doc) uses the same commit.
- The Assistant export as delivered, built from the `kiln_server` branch of PR 352. It has no commit in this repository, and it stays outside it.

Later fixes from harness-tuner, while two copies of the knowledge exist (functional spec 7.5): diff harness-tuner's knowledge folder (`src/kiln_harness_tuner/agent_files/skills/kiln-harness-tuner-knowledge/`) from the recorded commit to its head; port each change by hand, with the rewrites of batches 7 and 8; run `skill_checks build` and the checks; then update the recorded commit. The recorded commit lives in `.agents/skills/knowledge-maintenance/SKILL.md`, which also holds this procedure. A fix made first in Kiln's copy is not ported back.

Not in this port: the harness-tuner skills `kiln-task-setup` and `experiment-costing`, and the skill-authoring guide. Each is a separate decision (architecture section 8).

**Fixed lists and named outputs.** These are decided here, or are an output of one batch with the rule that decides them:

- *The table of main app pages*: written down in 4.3. *The blocked capabilities and their pages*: written down in 4.4.
- *The size allow-list* of `test_no_file_over_body_limit`: empty. No file of either source, and no generated endpoint doc, is over 30,000 characters today. Rule: a hand-written file over the limit is split, never listed. A generated endpoint doc or a copied help article over the limit may be listed, with a comment that gives the reason.
- *The banned-terms check and generated files*: `tree-banned-term` does not cover `references/knowledge/api_docs/` (section 8).
- *The operation-to-endpoint map* (`OPERATION_ENDPOINTS`): the first output of batch 7, a table in the batch's pull request, one row for each of the 54 gateway operation names: the operation, the REST method and path, and the endpoint doc path or `none`. Rule: an operation maps to the REST endpoint that its handler in harness-tuner's `gateway/ops.py` calls. When the handler calls several, it maps to the one that makes the change, and the lever text names the others in its steps. An operation with no REST call, or whose endpoint is MCP-blocked, maps to `none`. Batch 8 uses the same table for the wording. The table is not kept in the repository.
- *The overlap groups* (`OVERLAP_GROUPS`): the first output of batch 13, a list in the batch's pull request. A group is one subject that both sources teach, with the knowledge documents and the Assistant files that teach it. The research found 11 subjects: improving a prompt; model choice and the cost and speed ladder; run parameters; structured output mode; an eval that is itself the problem; running an improvement loop; skills; tools and code tools; grounding and RAG; cheaper or faster as a goal; creating a task and a run config. Rule for membership: an Assistant file is in a group when one of its sections gives advice on when or why to use the thing that a lever, technique, smell or playbook of the group covers. A group whose knowledge side is only a harness-tuner skill that is not ported gets no line.

| # | Batch | What changes (counts from the research) | Rule for hard cases | Verified by |
|---|---|---|---|---|
| 1 | Import the Assistant files; normalise references | Add 66 files. `SKILL.md` gets front matter. 46 `skill(name=…, resource=…)` calls in 19 files become plain paths; 6 bare `skill()` verbs become "read"; the access-rule section goes. 75 bare skill-file names (22 files) and 17 bare API-doc names (7 files) become full paths. Of 7 `../` links in help articles, 6 leave the copied set and become public URLs, and 1 becomes a root path (the import script of C8 does these) | 2 `skill()` mentions describe the Kiln product feature and stay. A base name with two matches is fixed by hand | `tree-path`, `tree-relative`, `tree-bare-name`, `tree-call-syntax`, `tree-file`; hygiene review |
| 2 | Model info | About 70 mentions of the three Assistant tools in 13 files (`model_work.md` 21, `improve_task.md` 13, `learn_about_kiln.md` 10) become the model info endpoints through `call_kiln_api`: list and search → `GET /api/model_info/models`, details → `GET /api/model_info/model_details`, providers → `GET /api/model_info/providers`. Rewrite the defining section of `model_work.md` | "MCP tool" stays only where it means Kiln's tool-server feature (17 hits in 7 files to review) | `tree-banned-term`; `tree-path` for the 3 endpoint docs |
| 3 | Link templates | About 160 app links in 25 files (108 in backticks, 52 link targets, 51 distinct paths) get `http://localhost:8757`. Rewrite the 4 rule statements, the 10 per-file link tables and the 2 "external URL" definitions | About 6 regex hits are API paths (`/api/…`): leave them | `tree-app-link`; `test_address_replacement_covers_every_app_link` |
| 4 | Identity and on-demand loading | Rewrite `SKILL.md` to 4.3: persona (4 uses of the name), always-in-a-mode, greeting, session start, the compaction rule, the no-repeat-load rules. Rewrite the Session Start and intent-check sections of 3 modes, and `establish_intent.md` | A rule that only makes sense for an always-present system prompt is deleted, not reworded. Rules apply "while you do Kiln work" | `test_skill_md_has_the_required_parts`, `test_skill_md_size`; `tree-banned-term` (scope `SKILL.md`); owner reads `SKILL.md` |
| 5 | UI-only and approval wording | 11 statements in 14 files, against the block list. 19 endpoint docs that the skill names belong to endpoints the Assistant is denied; each is looked up. The agent now does the work for: running an eval, MCP server wiring, RAG setup and indexing, code tools, judges, task from a tool, dataset download. It still sends the user to the app for every capability of the table in 4.4, which is built from the block list (server doc 6.3) and is not restated here: each gets the C10 wording with the app link of that table. The two "not connected" texts of 4.4 (Kiln Pro, provider) are written in this batch. About 55 approval hits in 20 files: "requires approval" becomes "ask the user first", or goes | The endpoint has a doc in `api_docs/` → write the API workflow. No doc → it is blocked: "ask the user to do this in the app", with the link of 4.4. A blocked capability that 4.4 does not list is reported, and 4.4 gets a row. Product advice (Eval Builder, data-guide jobs) stays as advice. The destructive-action rule stays | `tree-path`; `tree-banned-term` (`UI-only`, `approval-gated`, `requires approval`, `requires user approval`); `test_no_skill_file_names_a_blocked_endpoint`, which lands with this batch |
| 6 | Help-article URLs | A one-off import script (C8; not kept in the repository) adds `online_url` to the 34 articles and removes `<figure>`, `<img>` and Markdown images whose file is not in the tree (79 and 80 tags). `docs_index.md` is regenerated with `skill_checks build`. Other GitBook markup stays | No hand edits except spelling | `tree-front-matter` (every article has its `online_url`); docs index current; `misspell` |
| 7 | Knowledge import and link rewrite | Add 74 files in 4 folders. 367 file-relative links become root paths (levers 18, techniques 168, smells 47, playbooks 134). `gateway_ops` (34 entries, 7 levers) becomes `api_docs`. `detected_by` and `detectors` leave 15 smells. The lever heading is renamed in 7 files. Write the 2 index files and run `build` | First write `OPERATION_ENDPOINTS` (rule above) from harness-tuner's `gateway/ops.py` (reference only; no code is copied). An operation that maps to `none` gets no `api_docs` entry; batch 8 rewords the text | Every knowledge rule except `size`; `index` current; `tree-relative` |
| 8 | Gateway-tool and role wording | 83 gateway operation names in 12 files (72 in the levers); "gateway" 5; role names 95 in 38 files; "the tuner / the loop / this run" 40 in 25; other harness-tuner skills by name 27 in 13; 1 run-folder path. 5 smells get "how to measure this yourself" with the number (prompt over 200,000 characters; tool description over 4,096; skill description over 1,024; more than 40 tools; model older than 8 months). `levers/output_mode.md` and `smells/tools-on-a-live-server.md` are over the size limit after batch 7 and are shortened | A role becomes "you". An operation becomes its endpoint doc path from `OPERATION_ENDPOINTS`. A sentence that only works inside the tuner loop is deleted. A hard limit of the tuner becomes advice or goes. "experiment", "budget", "hypothesis" stay | `tree-banned-term` (scope: the knowledge trees); knowledge `size`, `sections` |
| 9 | Train/val/test | New `references/knowledge/train_val_test.md`: tune on train; confirm on val by running the evals on val and reading the metrics, without reading the val data; never read test; good practice, not enforced. 79 split mentions in 40 files are reviewed | A file may use the words. Only the central file states the rule. Any other statement of the rule is replaced by the path | `tree-split-pointer`; owner reads the file |
| 10 | Memory | New `references/knowledge/memory.md` (at most 12,000 characters) from harness-tuner's `memory` skill (28,273 bytes, 9 gateway mentions): the 6 Memory endpoints with their doc paths, tags, write discipline. Listed in `SKILL.md` and the modes | Run and loop scopes go | `tree-path`, `tree-unreachable`, `tree-banned-term` |
| 11 | Code tools and MCP wiring | Rewrite `code_tools.md`, the wiring part of `tools.md` and of `subagents.md` for the API: read the trust state, ask the user before granting code trust or adding a local MCP server (both run code on the Kiln machine), create, test, iterate. New `code_tool_authoring.md` and 8 files in `code_tool_wrappers/` from harness-tuner's authoring skill (10 files, 46,063 bytes, 16 gateway mentions) | Say what a coding agent can do that the Assistant cannot: run the tool's tests | Tree rules; `test_wrapper_templates_compile` |
| 12 | Project files guide | New `references/knowledge/working_with_project_files.md` with the three rules of functional spec 7.4. Listed in `SKILL.md` and 3 modes | It says nothing about val or test data | `tree-unreachable` |
| 13 | Wire the knowledge into the modes; final checks | `modes/improve_task.md` lists the two index files and the usual path (smell or playbook → technique → lever; prefer a playbook). First write `OVERLAP_GROUPS` (rule above). Each Assistant file of a group gets one "See also" line with the full paths of the group's knowledge documents. `optimize_quality.md` and `optimize_performance.md` point to the playbooks in place of their own ladders. Then: no pending rule, `misspell`, `checks.sh`, wheel file count | The Assistant file owns "how to do it in Kiln". The knowledge document owns "when and why". Where the two give opposite advice, the knowledge wins (proposed; architecture section 11, item 1) | `tree-unreachable`; `test_no_rule_is_pending`; all checks |
| 14 | Server and tool texts | Tune the five constants of `texts.py` against the final `SKILL.md`: `SERVER_INSTRUCTIONS`, `SKILL_TOOL_DESCRIPTION`, `PATH_DESCRIPTION`, `CALL_KILN_API_DESCRIPTION`, and `WHAT_KILN_IS` only together with the stub skill text of the install guide. Same terms and the same example path as the skill | The limits win over wording: the first 500 characters of the instructions stand alone, and the whole is under 4,000; the skill description has 100 to 150 words with the trigger rule in the first 500 characters. `PATH_DESCRIPTION` keeps the text of functional spec 6.1 unless the owner agrees to a change | `test_texts.py` and the schema snapshot of `test_server.py` (server doc, section 10); `test_description_is_100_to_150_words_and_front_loaded`; `test_example_paths_exist` |

`BANNED_TERMS` (test data; a term is matched as a whole token):

| Scope | Terms |
|---|---|
| Whole tree | `kiln-chat`, `model_info_featured`, `model_search`, `model_info` (not after `/` or `_`), `compacted_digest`, `UI-only`, `approval-gated`, `requires approval`, `requires user approval` |
| `SKILL.md` | `Kiln Assistant`, `always in context`, `turn 0` |
| Knowledge trees | the 54 operation names of harness-tuner's gateway (names only, from its `gateway/ops.py`), `install_skill_bundle`, `gateway`, `the tuner`, `harness-tuner`, `kiln-harness-tuner`, `the planner`, `the builder`, `the analyzer`, `the probe`, `scratch folder` |

**Needs a person.** The items are listed once, in [architecture.md](../architecture.md) section 11. Their gates in this phase:

- Item 5, the sandbox wording (the statement that user code runs with no network or filesystem sandbox, functional spec 15): before batches 5 and 11 merge.
- Item 5, the public-source claims: the 19 priors in the knowledge are all marked `Source: public`, and the tree holds no link. Before batch 7 merges.
- Item 1, the owner's read of `SKILL.md` (after batch 4) and of `train_val_test.md` (after batch 9), and the stance rule of batch 13.

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
| `skill_checks/test_shipped_skill.py` | 4, 5, then per batch in 6 | Step 4: `test_the_shipped_tree_passes_every_check` (with `PENDING_RULES`), `test_the_catalogue_index_exists` (`skill_files.API_CATALOGUE_INDEX_PATH` is a file of the tree), `test_no_file_over_body_limit` (each file at most 30,000 characters; the allow-list of section 9). Step 5: `test_the_shipped_knowledge_passes_every_check`, `test_each_template_gives_a_valid_document`, `test_the_maintenance_skill_names_the_commands`. Step 6, with the batch that makes each pass: `test_docs_index_is_current` (batch 6), `test_the_generated_blocks_are_current` and `test_a_document_of_each_type_exists` (batch 7), `test_example_paths_exist` (the paths in `SKILL_TOOL_DESCRIPTION`, `PATH_DESCRIPTION` and `HINT`; batch 1), `test_address_replacement_covers_every_app_link` (no file holds `127.0.0.1:8757`, `https://localhost:8757`, or `localhost:8757` without `http://`: forms the replacement would miss; batch 3), `test_skill_md_has_the_required_parts` and `test_skill_md_size` (batch 4), `test_wrapper_templates_compile` (batch 11), `test_no_rule_is_pending` (batch 13) |

`test_no_skill_file_names_a_blocked_endpoint` (C10). It needs the app, so it is in `app/desktop`. It reads the blocked operations from `make_app().routes` with `is_mcp_denied`, and turns each path template into a pattern in which a `{param}` matches `{…}` or one path segment, and which must not be followed by another path character. It searches every file of the shipped tree outside `references/knowledge/api_docs/`. A hit fails when every method of that path is blocked. When the path also has an allowed method (today only `/api/settings`: `GET` allowed, `POST` blocked), a hit fails only when the blocked method is on the same line. The generated reference already has no blocked endpoint (`test_committed_docs_match_the_block_list`).

The bundling test (collected data against the file index) is the server doc's, in `app/desktop/test_pyinstaller_hooks.py`; this doc has no copy of it. No test reaches the network. The manual checks of functional spec 16 exercise the content.

## Open items

To verify during implementation:

- **The generator pin** inside the real workspace (it was tested in a throwaway project), in build step 4.
- **The knowledge tooling on Python 3.10** (the source was read, not run there), and `ty` and ruff on the ported code, in step 5.
- **Help-article URLs.** The 34 `online_url` values come from the public sitemap; no URL was requested directly. Request each one in batch 6.
- **Attaching a skill to a run config** (batch 5): the Assistant text says the API cannot do it. Check against the generated endpoint doc.
- **`misspell`** over the ported text (batches 6 and 13).
- **`alwaysLoad`**: whether it holds in every Claude Code configuration. Manual sanity phase.

Owner decisions and person reviews are in [architecture.md](../architecture.md) section 11: item 1 (the stance conflict, and the owner's read of `SKILL.md` and `train_val_test.md`), item 2 (the home of the knowledge backlog), item 5 (the sandbox wording, the public-source claims, case studies). Section 9 above says before which batch each is needed. Follow-ups (the help-article refresh, the harness-tuner skills that are not ported) are in architecture section 8.
