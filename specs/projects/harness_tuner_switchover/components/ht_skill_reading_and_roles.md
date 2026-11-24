---
status: draft
---

# Component: How Harness Tuner Reads Kiln's Skill, and Its Role Entry Files

This document designs steps 10 and 11 of the [architecture](../architecture.md) build order. It covers [functional spec](../functional_spec.md) sections 5.1 to 5.5, and the parts of sections 6 and 7 that belong to them. The sibling document [ht_api_switch_and_removals.md](ht_api_switch_and_removals.md) covers the API switches, the removals, the start-up order, the audit and the demo run.

Conventions:

- **HT** is the harness-tuner repository at commit `b49f159`. HT paths are under `src/kiln_harness_tuner/` unless they start with `tests/` or `docs/`. Line numbers are of that commit.
- **Kiln paths** are from `app/mcp/kiln_mcp_server/skill/`. Each one was checked against the build branch at commit `5522a7b9` (after its phase 18).
- A code block with no language is a signature or pseudo-code. It is not final code.
- "Per the Kiln component doc" marks a name that a sibling Kiln document fixes.
- The rulings of architecture section 10 are applied in the body. Section 10 lists the limits that are accepted, and section 11 the one point that is still open.

## 1. `SkillReader`

### 1.1 Module and signatures

New module `kiln_skill.py`. It is the only HT module that imports MCP client code.

```
SKILL_TOOL = "kiln_skill"
MCP_PATH = "/mcp"
CONNECT_TIMEOUT_SECS = 5.0
READ_TIMEOUT_SECS = 20.0
CALL_TIMEOUT_SECS = 30.0

class KilnSkillError(Exception):
    """Kiln's skill could not be read. The message is plain text for a person or an agent."""

class SkillSource(Protocol):
    async def read(self, path: str) -> str: ...

class SkillReader:                                  # implements SkillSource
    def __init__(self, kiln_host: str) -> None
    url: str                                        # f"{kiln_host.rstrip('/')}{MCP_PATH}"
    async def read(self, path: str) -> str          # cached; raises KilnSkillError
```

- `read("")` and `read("  ")` raise `KilnSkillError("give a path")`. HT's own code never asks for the root file.
- `SkillSource` is the type that the gateway and the loop code hold. Tests pass a fake (1.7).

### 1.2 The MCP client calls

HT's lock file has `mcp` 1.30.0. One uncached read does this, in this order:

| Step | Call (package `mcp` 1.30.0) |
|---|---|
| 1 | `httpx.AsyncClient(timeout=httpx.Timeout(CONNECT_TIMEOUT_SECS, read=READ_TIMEOUT_SECS))`, as a context manager |
| 2 | `mcp.client.streamable_http.streamable_http_client(url, http_client=client, terminate_on_close=False)`, which yields `(read_stream, write_stream, get_session_id)` |
| 3 | `mcp.ClientSession(read_stream, write_stream, read_timeout_seconds=timedelta(seconds=READ_TIMEOUT_SECS), client_info=Implementation(name="kiln-harness-tuner", version=__version__))`, as a context manager |
| 4 | `await session.initialize()` |
| 5 | `result = await session.call_tool("kiln_skill", {"path": path})`, a `mcp.types.CallToolResult` |
| 6 | Leave the three context managers. The session is closed |

- The whole of steps 1 to 6 is inside `asyncio.timeout(CALL_TIMEOUT_SECS)`.
- `streamable_http_client` is used, not `streamablehttp_client`, which is deprecated in 1.30.0.
- `pyproject.toml` raises the floor from `mcp>=1.10.1,<2` to `mcp>=1.30,<2`. The version that first has `streamable_http_client` was not checked, so the floor is the locked version. The `<2` ceiling stays: `gateway/server.py` imports `mcp.server.fastmcp`.
- Kiln's server is stateless and answers POST only (`server.py`, `McpEndpoint`). The SDK opens its GET stream only when it holds a session id (`streamable_http.py:285`), and a stateless server gives none. `terminate_on_close=False` states that no DELETE is sent.
- One read is four POST requests: `initialize`, the `notifications/initialized` notice, `tools/call`, and a `tools/list` that the SDK sends after the call to check the result against the tool's schema.

### 1.3 From the tool result to text, and errors

| Case | Result |
|---|---|
| `result.isError` is false | The text is `"\n".join(block.text for block in result.content if isinstance(block, mcp.types.TextContent))`. Kiln sends one text block (`skill_tool.py`, `_text_result`). An empty text raises `KilnSkillError("Kiln's skill gave an empty answer for <path>")` |
| `result.isError` is true | `KilnSkillError(<the joined text>)`. The text is Kiln's own message, for example ``No skill file at `x`.`` with the files of the nearest folder (`skill_files.py`, `_not_found_message`) |
| The leaf exception is an `httpx.TransportError` (connect, timeout), or the whole call times out | `KilnSkillError("Kiln's skill could not be read: Kiln did not answer at <url> (<reason>)")` |
| The leaf is `mcp.McpError` with the text `Session terminated` | The SDK reports HTTP 404 this way. `KilnSkillError("Kiln's skill could not be read: this Kiln has no MCP server at <url>. Update Kiln.")` |
| The leaf is `httpx.HTTPStatusError` with status 421 | `KilnSkillError("Kiln's skill could not be read: Kiln refused the Host header of <url>. Give --kiln-host a loopback address, for example http://localhost:<port>.")` |
| The leaf is `httpx.HTTPStatusError` with another status | `KilnSkillError("Kiln's skill could not be read: HTTP <status> from <url>")` |
| Any other exception | `KilnSkillError("Kiln's skill could not be read: <type>: <text>")`, cut to 500 characters |

- The transport runs in an anyio task group, so every transport failure arrives as an `ExceptionGroup`. `read` catches `Exception` (an `ExceptionGroup` is one), takes the first leaf exception, and maps it with the table. `asyncio.CancelledError` is not caught.
- A `KilnSkillError` is never cached.

### 1.4 The URL and the Host header

- The URL is HT's Kiln host plus `/mcp`: `--kiln-host`, default `http://localhost:8757` (`kiln.DEFAULT_KILN_HOST`). The gateway gets the host as `--kiln-host`, as today.
- HT does not set or rewrite the Host header. httpx sends the host and port of the URL.
- A Kiln that is bound to a loopback address accepts only loopback names, with any port: `127.0.0.1`, `localhost`, `[::1]` (`addresses.py`, `transport_security_for`). Another name gives HTTP 421, also when REST on the same address works (REST has no such check). The table in 1.3 gives the message. A Kiln on another bind has no check.
- HT sends no `Origin` header.

### 1.5 The cache

- One dict per `SkillReader`: the path as given, stripped, to the text. No expiry, no size limit: the tree is about 2 MB.
- A gateway process holds one reader for its life, which is one agent session. Loop code holds one reader per run, at `Ctx.skill_reader`, made in `cli.build_ctx` from `target.kiln_host`.
- The start-up check runs before the run has a `Ctx`. It holds its own reader, for the check only (sibling document, section 3).
- Two reads of one path at the same time may both fetch. Both store the same text.

### 1.6 What must be proved first, against a real Kiln

This is the first task of step 10. No other HT work starts before it passes. Run a 20-line script against a Kiln build of spec one.

A first check was made for this document, with `mcp` 1.30.0 in HT's environment, against a stand-in server built the way Kiln builds its own (`FastMCP(stateless_http=True, json_response=False)`, POST only). Steps 1 to 6 returned the text, an `isError` result carried its message, the errors surfaced as 1.3 says, and 93 reads at 8 at a time took about 2 seconds. It is not a proof against Kiln: the mount, the Host check and the real tool were not in it. The proofs:

| # | Proof |
|---|---|
| 1 | Steps 1 to 6 of 1.2 return the text of `references/improving_agents/index.md` |
| 2 | Leaving the context managers does not hang and raises nothing. No GET and no DELETE is needed |
| 3 | `<host>/mcp` with no trailing slash is accepted, or its redirect is followed |
| 4 | An unknown path gives `isError` true and Kiln's message |
| 5 | With Kiln stopped, the exception that surfaces is mapped by 1.3 |
| 6 | A non-loopback host name against a loopback bind gives HTTP 421, and 1.3 maps it |
| 7 | 8 reads at the same time work. Record the time of one read, and of the 93 reads of the start-up check (section 8) |
| 8 | The same read works from a gateway process that Claude Code starts. The gateway already reaches Kiln's REST from there |

If proof 1 or 2 fails, stop and report: architecture decision 1 cannot hold as written.

### 1.7 The fake for tests

In `tests/fake_kiln.py`:

```
class FakeSkillReader:                              # implements SkillSource
    def __init__(self, root: Path = FIXTURE_SKILL, *, fail: str | None = None) -> None
    reads: list[str]                                # every path asked, in order
    async def read(self, path: str) -> str
```

- It reads `root / path`. A missing file raises ``KilnSkillError("No skill file at `<path>`.")``. With `fail` set, every read raises `KilnSkillError(fail)`.
- `FIXTURE_SKILL` is `tests/fixtures/kiln_skill/`. It holds text written for the tests, not a copy of Kiln's files: `references/improving_agents/index.md` with a "Smells" table of the 15 ids, and one small file per smell with a `title` in its front matter.
- No test opens an MCP connection. `SkillReader` itself has unit tests that patch `streamable_http_client` and `ClientSession` (section 9).

## 2. The gateway tool `kiln_skill`

| Part | Design |
|---|---|
| Request model, `gateway/models.py` | `class KilnSkillRequest(In): path: str \| None = Field(default=None, max_length=300, description="The path of one file of Kiln's skill, for example references/improving_agents/index.md.")` |
| Entry in `OPS`, `gateway/ops.py` | `("kiln_skill", m.KilnSkillRequest, "One file of Kiln's skill, as text. Give its path, for example references/improving_agents/index.md.")` |
| Plain-text marker | `PLAIN_TEXT_OPS = frozenset({"kiln_skill"})`, after `OPS` |
| Method | `async def kiln_skill(self, req) -> str`: refuse a blank path; `return await self.skill.read(path)`; a `KilnSkillError` becomes `GatewayError(str(exc))` |
| The reader | `Gateway.__init__(self, call, state, skill: SkillSource \| None = None)`. `gateway/server.py:main` passes `SkillReader(args.kiln_host)`. With `None`, the tool raises `GatewayError("Kiln's skill is not set up in this gateway")` |
| No path | `GatewayError("give a path: name one file of Kiln's skill, for example references/improving_agents/index.md. Your role skill names the file to read.")` |
| The answer | The file's text, not JSON (decision 4). `dispatch` returns a `str` result as it is when `len(text) <= ANSWER_MAX_CHARS` (40,000) |
| Over the cap | `dispatch` calls `gateway.capped(text)`. The answer is then the existing `AnswerPart` JSON, and `get_answer_part` gives the rest. The largest file today is 27,177 characters |
| An error | `gateway/server.py:_tool`: for an op in `PLAIN_TEXT_OPS`, a `GatewayError` is raised as `mcp.server.fastmcp.exceptions.ToolError(str(exc))`, so the MCP result has `isError` true. FastMCP puts `Error executing tool kiln_skill: ` before the message. Every other tool keeps today's `{"error": …}` text |
| Path limits | None. The whole skill is passed through. `path="SKILL.md"` reads the root file |

### 2.1 Roles

`_KNOWLEDGE = ("kiln_skill",)` is added to these `ROLE_OPS` entries. A role gets the tool when its skill, its entry file or its prompt names a Kiln path after the re-pointing (section 5).

| Role | Gets it | Because it names |
|---|---|---|
| `batch_plan` | yes | Its entry file; levers, techniques, playbooks; memory; the costing file, when the pre-flight has found it (5.2) |
| `create_experiment_rc` | yes | Its entry file; levers, techniques; the code tool authoring file and templates; memory; the run config file |
| `analyze_experiment_results` | yes | Its entry file; memory |
| `baseline_review` | yes | Its entry file; the smell documents |
| `report_writer` | yes | Its entry file; memory |
| `probe` | yes | The code tool authoring file; memory |
| `promote_best` | yes | Memory |
| `preflight`, `describe_eval`, `eval_build` | no | Their prompts name no Kiln path |
| `integrity_review`, `generality_review` | no | They have no MCP server |

`role_tools`, the hook (`gateway/hook.py`), `DEFAULT_ALLOWED_TOOLS` and `mcp_tool_names` read `ROLE_OPS`, so they need no other change.

### 2.2 The gateway skill

`agent_files/skills/kiln-harness-tuner-gateway/SKILL.md` gets:

- A new sub-section "Kiln's skill" under "The operations", with the row: `kiln_skill` | `path` | the file's text as Kiln serves it, plain text and not JSON; an unknown path is an error that lists the files of the nearest folder.
- One sentence: "The rules for reading Kiln's skill are in your prompt, under 'Reading Kiln's skill'."
- The tool in each role's row of "Which role has which operations".
- The map of section 7, in a new section "Kiln endpoints and your tools".

`test_every_gateway_operation_is_documented_in_the_gateway_skill` already fails when the row is missing.

## 3. Loop code: `_smell_titles`

`smells/run.py:440-451` becomes async, and its two callers (`_review`, `run_detectors`) await it.

```
async def _smell_titles(ctx: Ctx) -> dict[str, str] | None:
    if ctx.smell_titles is not None: return ctx.smell_titles          # new Ctx field, default None
    if ctx.skill_reader is None: log knowledge_unreadable; return None
    try:
        index = await ctx.skill_reader.read(SMELL_INDEX_PATH)
        ids = smell_ids(index)                                        # raises KilnSkillError when empty
        titles = {i: smell_title(await ctx.skill_reader.read(SMELL_PATH.format(id=i)), i) for i in ids}
    except KilnSkillError as exc:
        ctx.log.event("knowledge_unreadable", reason=str(exc)); return None
    ctx.smell_titles = titles; return titles
```

`SMELL_INDEX_PATH = "references/improving_agents/index.md"`. `SMELL_PATH = "references/improving_agents/smells/{id}.md"`. A failure is not cached, so the next call tries again. The fallback is today's: `None`, the review runs with `known_smells=[]`, and findings are kept unchecked.

**`smell_ids(index_text) -> list[str]`**, in `kiln_skill.py`:

1. Split the text into lines. A line that starts with `## ` opens a section. The section "Smells" is the one whose line, stripped at the right, is exactly `## Smells`.
2. In that section, take each line that starts with `|`. Split it on `|`. Strip the second element (the first cell).
3. Keep it when it matches ``^`references/improving_agents/smells/([a-z0-9][a-z0-9-]*)\.md`$``. The id is group 1. The header row, the `---` row and the `<!-- … -->` marker lines do not match.
4. Return the ids in table order, each once. No id raises `KilnSkillError("no smell id in the Smells table of references/improving_agents/index.md")`.

**`smell_title(file_text, smell_id) -> str`**, in `kiln_skill.py`. No YAML parser is used:

1. When the first line is `---`, the front matter is the lines up to the next `---` line. The title is the first front matter line that matches `^title:\s*(.+?)\s*$`. A pair of matching quotes around it is removed.
2. Else, or with no `title` line, the title is the first line after the front matter that matches `^# (.+?)\s*$`.
3. Else the title is the id.

Both rules were run on the 16 real files of the fresh copy: the index gives the 15 ids, and each smell file gives a `title` that equals its `# ` heading. A file other than the root file is served with its front matter (`skill_files.py`, `read_skill`).

## 4. Role entry files

Each entry file moves from `agent_files/skills/kiln-harness-tuner-knowledge/references/` to `references/knowledge-entry.md` of a role skill (architecture 5.3). The name is fixed by the architecture. It is chosen so that it cannot be mistaken for Kiln's own `references/knowledge/` folder. Every new file starts with this fixed paragraph, after its title:

> A path in this file that starts with `references/improving_agents/`, `references/levers/` or `references/knowledge/` is a file of Kiln's skill. Read it with the gateway tool `kiln_skill`. It is not a file on disk.

| Today | New path | Hand-written part kept | Generated table | Becomes this line |
|---|---|---|---|---|
| `planner.md` | `kiln-harness-tuner-batch-selection/references/knowledge-entry.md` | Lines 1 to 50 ("How to use the knowledge", the list of lever ids, the "Applies to" note), and the two-line intro of each section | `smells` | "The smells: read the section "Smells" of `references/improving_agents/index.md`." |
| | | | `playbooks-order`, `playbooks-goal`, `playbooks-failure`, `playbooks-eval`, `playbooks-design` | One line each, with the sections "Order of work", "Goals", "Failure patterns", "Eval problems" and "Design" of the same file |
| `builder.md` | `kiln-harness-tuner-experiment-build/references/knowledge-entry.md` | Lines 1 to 30 | `techniques` | "The techniques: read the section "Techniques" of `references/improving_agents/index.md`. It does not list dormant techniques." |
| | | | `levers` | The hand-kept table 4.2 |
| `analyzer.md` | `kiln-harness-tuner-experiment-analysis/references/knowledge-entry.md` | Lines 1 to 29, and the section intros | `playbooks-failure`, `playbooks-eval` | One line each, with the sections "Failure patterns" and "Eval problems" |
| `smells.md` | `kiln-harness-tuner-baseline-review/references/knowledge-entry.md` | Lines 1 to 24 | `smells-detail` | "The smells: read the section "Smells" of `references/improving_agents/index.md`." Then the hand-kept table 4.1 |
| `report.md` | `kiln-harness-tuner-report/references/knowledge-entry.md` | Lines 1 to 15 | `smells`, `playbooks`, `techniques` | Three lines: "Smells"; the five playbook sections; "Techniques" |
| `technique-index.md` | Removed | Its one rule ("Prefer a playbook…") is already in step 4 of the planner's file | `techniques` | Nothing. Kiln's index has the table "Techniques" |

Edits inside the kept parts:

| File | Today | New |
|---|---|---|
| planner, line 4; builder, line 18 | `[the knowledge skill](../SKILL.md)` says in "How to read these documents" | `references/improving_agents/index.md` says in "How to read these documents" |
| planner, line 30 | `[dealing-with-a-noisy-eval](playbooks/dealing-with-a-noisy-eval.md)` | `references/improving_agents/playbooks/dealing-with-a-noisy-eval.md` |
| planner, line 35 | find it in `[technique-index.md](technique-index.md)` | find it in the section "Techniques" of `references/improving_agents/index.md` |
| builder, lines 12 to 14 | "A lever document says how the tuner creates and changes that part of the harness: the gateway operations, the rules of the object and the limits." | "A lever document says how to change that part of the harness ("How to change it") and its limits ("Limits"). It names Kiln endpoints: the table "Levers" below gives your gateway tools for each lever." |
| smells, lines 17 to 20 ("Detected by" says who…) | Describes a column of the generated table | Describes table 4.1 |

### 4.1 Hand-kept table: the smells that code detects (baseline-review file)

| Smell id | Detected by | Detector id in your input |
|---|---|---|
| `very-long-prompt` | code, agent | `long_prompt` |
| `very-long-tool-description` | code | `long_tool_description` |
| `very-long-skill-description` | code, agent | `long_skill_description` |
| `too-many-tools` | code | `many_tools` |
| `old-model` | code | `old_model` |

Below it: "Every other smell is detected by `agent`: a reader of the design." The values are today's `detected_by` values (`smells.md:29-45`) and today's detector ids. The architecture asks for no test of this table. The audit checks it.

### 4.2 Hand-kept table: the gateway tools of each lever (experiment-build file)

| Lever | Gateway tools |
|---|---|
| `references/levers/model.md` | `get_run_config`, `list_models`, `get_model_details`, `list_providers`, `create_run_config` |
| `references/levers/new_tool.md` | `list_code_tools`, `get_code_tool`, `get_tool_definition`, `trust_code_tools`, `test_code_tool`, `create_code_tool`, `create_run_config`, `archive_code_tool` |
| `references/levers/output_mode.md` | `get_run_config`, `get_model_details`, `create_run_config` |
| `references/levers/params.md` | `get_run_config`, `get_model_details`, `create_run_config` |
| `references/levers/prompt.md` | `get_run_config`, `list_prompts`, `get_prompt_text`, `create_prompt`, `create_run_config` |
| `references/levers/skill.md` | `list_skills`, `get_skill`, `get_skill_content`, `install_skill_bundle`, `export_skill_bundle`, `create_run_config`, `archive_skill` |
| `references/levers/tool_config.md` | `get_run_config`, `list_available_tools`, `get_tool_definition`, `list_code_tools`, `create_run_config` |

The rows are today's `gateway_ops` values (`builder.md:69-75`). The skill row adds the two bundle tools, which become gateway tools in step 12. The "Description" column goes: `references/levers/index.md` has it. New test `test_the_lever_tool_table_names_real_gateway_tools`: the table has exactly the 7 lever ids, and each tool is in `gateway.ops.OPS` and in `ROLE_OPS["create_experiment_rc"]`.

## 5. Links to re-point

"Kiln:" marks a path in Kiln's skill. "Entry file" is `references/knowledge-entry.md` of the role's own skill. Skill files are under `agent_files/skills/`.

| File | Line | Today | New |
|---|---|---|---|
| `agents/batch_plan.md` | 8 | `references/planner.md` of the `kiln-harness-tuner-knowledge` skill | `references/knowledge-entry.md` of your `kiln-harness-tuner-batch-selection` skill |
| `agents/create_experiment_rc.md` | 7 | the `kiln-harness-tuner-code-tool-authoring` skill | Kiln: `references/knowledge/code_tool_authoring.md` |
| | 7-8 | `references/builder.md` of the knowledge skill | `references/knowledge-entry.md` of your `kiln-harness-tuner-experiment-build` skill |
| `agents/baseline_review.md` | 5 | `references/smells.md` of the knowledge skill | `references/knowledge-entry.md` of your `kiln-harness-tuner-baseline-review` skill |
| `agents/analyze_experiment_results.md` | 5-6 | `references/analyzer.md` of the knowledge skill | `references/knowledge-entry.md` of your `kiln-harness-tuner-experiment-analysis` skill |
| `agents/report_writer.md` | 6 | `references/report.md` of the knowledge skill | `references/knowledge-entry.md` of your `kiln-harness-tuner-report` skill |
| `…-batch-selection/SKILL.md` | 27, 1160 | Load the `memory` skill | Kiln: `references/knowledge/memory.md`, and the format files of 5.1 |
| | 28, 750, 1166 | the `experiment-costing` skill | No change until the pre-flight finds the port in Kiln's skill (architecture ruling 22). Then: Kiln: the costing file, by its full path |
| | 433 | the knowledge skill's playbooks … and the technique | Kiln's playbooks … and the technique (prose only) |
| | 463-464, 471, 627, 1162-1163 | `references/planner.md` of the knowledge skill | the entry file |
| | 531 | the knowledge lever `levers/output_mode.md` | Kiln: `references/levers/output_mode.md` |
| | 806-807 | `techniques/model-swap-inside-a-class.md`, `techniques/decision-model-for-a-classifier.md` | Kiln: `references/improving_agents/techniques/<same names>` |
| | 906 | a lever document of the knowledge skill | a lever document of Kiln's skill (`references/levers/`) |
| | 912-913 | `techniques/<id>.md` | `references/improving_agents/techniques/<id>.md` |
| | 1069-1070 | `references/playbooks/dealing-with-train-wins-rejected-at-val.md` of the knowledge skill | Kiln: `references/improving_agents/playbooks/dealing-with-train-wins-rejected-at-val.md` |
| | 1129 | A memory-write-failure disclosure — `memory` skill | Kiln: `references/knowledge/memory.md`, "Write discipline"; you disclose it in your output |
| | 610, 628 | "How to confirm it", "What it blocks" | No change. Kiln's smell files have both headings |
| `…-baseline-review/SKILL.md` | 45-46 | code could not read the knowledge skill: use the ids of the table in `references/smells.md` | code could not read Kiln's skill: use the ids of the section "Smells" of Kiln: `references/improving_agents/index.md` |
| | 50-51, 124-125 | `references/smells.md` of the knowledge skill | the entry file |
| | 70, 74 | "How to recognise it", "How to confirm it" | No change |
| `…-experiment-analysis/SKILL.md` | 337 | the knowledge skill's playbook id, `references/analyzer.md` | Kiln's playbook id, from the entry file |
| | 387, 394 | the `memory` skill | Kiln: `references/knowledge/memory.md` |
| `…-experiment-build/SKILL.md` | 17, 321 | load `kiln-task-setup` | the lever of your item; Kiln: `references/knowledge/model_create_configs.md` ("Key Parameters", "Kiln Name Validation") for the run config fields and the name rules |
| | 18, 322 | `kiln-harness-tuner-code-tool-authoring` | Kiln: `references/knowledge/code_tool_authoring.md`. New sentence: "The tuner grants code tool trust itself, once per run, with `trust_code_tools`. Skip the steps that explain trust to a user or open the trust page." |
| | 58-60 | the knowledge lever `levers/model.md` (step 4); `levers/output_mode.md` | Kiln: `references/levers/model.md`, where it gives the output mode of a new model; `references/levers/output_mode.md`. The step number is not cited |
| | 89 | the `install_skill_bundle` MCP tool | the gateway tool `install_skill_bundle` (decision 15) |
| | 306, 325 | the `memory` skill | Kiln: `references/knowledge/memory.md` |
| | 323-325 | the knowledge skill's `references/builder.md` | the entry file |
| `…-experiment-build/references/skill-authoring.md` | 5-7 | Flat: `POST /skills` … as `kiln-task-setup` documents | Flat: a bundle folder that holds only `SKILL.md`, installed with `install_skill_bundle`. No gateway tool calls `POST /skills` |
| | 10-12, 84, 125, 143, 163 | the installer; `install_skill_bundle`; `export_skill_bundle` | The tool names stay. "the installer" becomes "the gateway". One new sentence at `export_skill_bundle`: "The export does not copy a binary asset. Its answer names each file that it skipped." (architecture ruling 16) |
| | 63 | The knowledge skill's playbook (lost in long instructions) | Kiln: `references/improving_agents/playbooks/lost-in-long-instructions.md` |
| `…-gateway/SKILL.md` | 271, 350 | The `memory` skill says what to write | Kiln: `references/knowledge/memory.md`; your role skill says what your role writes |
| `…-probe/SKILL.md` | 59, 112 | the `kiln-harness-tuner-code-tool-authoring` skill | Kiln: `references/knowledge/code_tool_authoring.md` |
| | 100, 113 | the `memory` skill | Kiln: `references/knowledge/memory.md` |
| `…-promote/SKILL.md` | 30, 264 | the `memory` skill | Kiln: `references/knowledge/memory.md` and `references/knowledge/memory_formats/baseline_and_val_records.md` |
| `…-report/SKILL.md` | 14, 326 | the `memory` skill | The same two files |
| | 260-261 | a candidate for the knowledge system | a candidate for Kiln's knowledge |
| The five moved entry files | — | 194 links in generated tables | Go with the tables (section 4) |

Not re-pointed, because the file goes: the 6 links and 2 names of `memory/SKILL.md`, the 9 template links of the code tool skill, `wrappers/README.md`, `experiment-costing/SKILL.md:264` and `kiln-task-setup/SKILL.md:60`. `agent_files/AGENTS.md` and the six other prompt templates name none of these. Comments in code that name "the knowledge skill" (`schemas.py:1756`, `smells/__init__.py`) are updated with the code.

### 5.1 The memory reference and its format files

HT's `memory` skill (28,273 characters) held the conventions and the formats in one file. Kiln's `references/knowledge/memory.md` (11,846 characters) holds the conventions. The formats are in five files under `references/knowledge/memory_formats/`. A role that reads a kind of record needs the file of that kind:

| Role | `memory.md` | Format files |
|---|---|---|
| `batch_plan` | yes | `experiment_records.md`, `issue_records.md`, `open_questions.md`, `screening_and_probe_records.md` |
| `analyze_experiment_results` | yes | `experiment_records.md`, `issue_records.md` |
| `create_experiment_rc` | yes | none |
| `probe` | yes | `screening_and_probe_records.md` |
| `promote_best`, `report_writer` | yes | `baseline_and_val_records.md`, `issue_records.md`; the report writer also `experiment_records.md` |

- A train-side role does not get `baseline_and_val_records.md` named. Reading it would do no harm: it holds formats, not records.
- `memory.md` is written for a chat agent. Its "Who writes" column, its "tell the user" sentences and its Orientation step that reads the `baseline` record do not fit a loop agent. Rules 1, 4, 5 and 6 of section 6 cover them, and each role skill keeps its own statement of what the role writes.

### 5.2 The other replaced skills

| Removed skill | Replacement | State on the fresh copy |
|---|---|---|
| `kiln-harness-tuner-code-tool-authoring` | `references/knowledge/code_tool_authoring.md` and the 8 files of `references/knowledge/code_tool_wrappers/` (`.md`, each a fenced template) | All 9 exist. `wrappers/README.md` has no file: the section "Wrapper templates" of the authoring file holds its table |
| `experiment-costing` | Its port in Kiln's skill | **Not found.** The nearest text is "Cost before you spend" in `run_an_experiment.md` and "Cost Estimation" in `model_work.md`. Neither is the port. See below |
| `kiln-task-setup` | `references/knowledge/model_create_configs.md`, the levers, HT's own `skill-authoring.md` | See below |

**The costing port is a pre-flight item** (architecture ruling 22; functional spec section 2). Until the port is in Kiln's skill: HT's `experiment-costing` skill is not removed, the planner's three pointers (section 5) are not changed, and the planner's skill goes on naming the HT skill. When the pre-flight finds the file: the three pointers name it by its full path, its path is added to `paths` of the contract list (section 8) and to `KILN_SKILL_PATHS`, and the sibling document removes the HT skill (its step 15d).

The unique facts of `kiln-task-setup`, checked on the fresh copy:

| Fact | In Kiln's skill |
|---|---|
| A run config's properties cannot change after creation | Yes: `model_create_configs.md:100` |
| The name rules | Yes: `model_create_configs.md` "Kiln Name Validation"; `create_task.md` "Name validation" |
| The tool id forms | Yes: `levers/tool_config.md:24-31`, `levers/skill.md:27` |
| A skill's reference files have no API | Replaced by the skill bundle routes (functional spec 3.9 and 4) |
| `turn_mode` is frozen; a multi-turn task has no schemas | Not found. No loop role needs it: no gateway tool creates a task |
| `kiln_tool::call_kiln_api` is hidden in the UI; use `kiln_api_mcp` | Goes with `kiln_api_mcp` |

## 6. The shared rules block

**The text.** It is exactly this:

```
## Reading Kiln's skill
Your knowledge files are in Kiln's skill. Read one with the gateway tool `kiln_skill`: give its path, for example `references/improving_agents/index.md`. A path that starts with `references/improving_agents/`, `references/levers/` or `references/knowledge/` is a path in Kiln's skill, not a file on disk. Kiln's skill is written for an agent in a chat with a person. You are not in a chat. These rules apply to every file that you read there:

1. You are not interactive. Where the skill says to ask the user, use your inputs and your output fields.
2. Where the skill names a Kiln endpoint, use the gateway tool for it. The `kiln-harness-tuner-gateway` skill carries the map from endpoint to tool. An endpoint with no tool is not available to you.
3. Where the skill says to check or measure something yourself, use the code's result when it is in your input.
4. Where the skill says to tell or report to the user, use your output field.
5. Your role skill wins over any procedure file in Kiln's skill.
6. Never read the `baseline` or the `val` memory record, if your role is on the train side.
7. Never read the project folder from disk.
```

The seven rules are the functional spec's (5.4), word for word.

**The single source.** A constant `KILN_SKILL_RULES` in `gateway/ops.py`, beside `ROLE_OPS`, with `def reads_kiln_skill(role: str) -> bool` (`"kiln_skill" in ROLE_OPS.get(role, ())`). No skill file and no template holds a copy.

**How it reaches each role.** `ClaudeCliDispatcher._render_prompt` (`dispatch/claude_cli.py:877`) builds every role's prompt, and the Codex and OpenCode dispatchers inherit it. It appends the block after the "Target" section when `reads_kiln_skill(agent)` is true. So the seven roles of 2.1 get it, and no other role does. This is how the scratch and target text reach every role today.

## 7. The map from endpoint to gateway tool

**Format.** A table in the gateway skill, between two marker comments:

```
<!-- BEGIN GENERATED: endpoint-tools -->
| Endpoint doc (in `references/knowledge/api_docs/`) | Gateway tool |
|---|---|
| `get_api_projects_project_id_tasks_task_id_run_configs.md` | `list_run_configs`, `get_run_config` |
| `delete_api_projects_project_id_memories_memory_id.md` | not available |
<!-- END GENERATED: endpoint-tools -->
```

**The source.** New constant in `gateway/ops.py`, after `OPS`: `OP_ROUTES: dict[str, tuple[str, ...]]`. It maps each tool to the Kiln routes it stands for, each as `"<METHOD> <path template>"` with Kiln's own parameter names, for example `"GET /api/projects/{project_id}/tasks/{task_id}/run_configs"`. A tool with no Kiln route has `()`: `get_val_summary`, `get_answer_part`, `kiln_skill`. The same constant feeds the route check of `contract.py` (sibling document, section 4), so a wrong template fails at the first live start.

**The script.** `tests/endpoint_tool_map.py`:

- `doc_name(method, path)`: Kiln's rule (`skill_checks/api_reference.py`, `endpoint_doc_name`): the method in lower case, `_`, then the path with no leading `/`, in lower case, the braces removed and each `/` replaced by `_`, then `.md`.
- `NOT_AVAILABLE`: a hand-kept tuple of the endpoint docs that Kiln's knowledge names and no tool serves.
- `build_table() -> str`: one row per doc name from `OP_ROUTES`, with its tools in `OPS` order, then one row per `NOT_AVAILABLE` entry. Rows are sorted by doc name.
- `python tests/endpoint_tool_map.py --write` rewrites the block in the gateway skill.

**The tests**, in `tests/test_agent_templates.py`: `set(OP_ROUTES) == set(OPS)` ("a tool has no entry" fails); the block in the gateway skill equals `build_table()`; no `NOT_AVAILABLE` entry is also a row from `OP_ROUTES`.

**Expected content today.** Kiln's knowledge (the levers, the improving-agents tree, `memory.md`, the memory format files, the code tool authoring file and its templates) names 27 endpoint docs. Recounted on the fresh copy:

| Endpoint doc | Gateway tool |
|---|---|
| `get_api_model_info_models.md` | `list_models` |
| `get_api_model_info_model_details.md` | `get_model_details` |
| `get_api_model_info_providers.md` | `list_providers` |
| `get_api_projects_project_id_available_tools.md` | `list_available_tools` |
| `get_api_projects_project_id_code_tools.md` | `list_code_tools` |
| `get_api_projects_project_id_code_tools_code_tool_id.md` | `get_code_tool` |
| `get_api_projects_project_id_memories.md` | `memory_list` |
| `get_api_projects_project_id_memories_by_ids.md` | `memory_get` |
| `get_api_projects_project_id_memories_summary.md` | `memory_summary` |
| `get_api_projects_project_id_skills.md` | `list_skills` |
| `get_api_projects_project_id_skills_skill_id.md` | `get_skill` |
| `get_api_projects_project_id_skills_skill_id_content.md` | `get_skill_content` |
| `get_api_projects_project_id_tasks_task_id_gen_prompt_prompt_id.md` | `get_prompt_text` |
| `get_api_projects_project_id_tasks_task_id_prompts.md` | `list_prompts` |
| `get_api_projects_project_id_tasks_task_id_run_configs.md` | `list_run_configs`, `get_run_config` |
| `get_api_projects_project_id_tasks_task_id_tools_tool_id_definition.md` | `get_tool_definition` |
| `patch_api_projects_project_id_memories_memory_id.md` | `memory_update` |
| `patch_api_projects_project_id_skills_skill_id.md` | `archive_skill` |
| `post_api_projects_project_id_code_tools.md` | `create_code_tool` |
| `post_api_projects_project_id_code_tools_code_tool_id_archive.md` | `archive_code_tool` |
| `post_api_projects_project_id_memories.md` | `memory_create` |
| `post_api_projects_project_id_tasks_task_id_prompts.md` | `create_prompt` |
| `post_api_projects_project_id_tasks_task_id_run_configs.md` | `create_run_config` |
| `post_api_projects_project_id_test_code_tool.md` | `test_code_tool` |
| `delete_api_projects_project_id_memories_memory_id.md` | not available |
| `get_api_projects_project_id_add_code_trust.md` | not available |
| `post_api_projects_project_id_skills.md` | not available |

That is 24 with a tool and 3 without, as the functional spec says. The generated table also has one row for each other route of `OP_ROUTES` (about 30 more, for example `post_api_statistics.md` | `compute_statistics`). When Kiln's skill text of functional spec section 4 lands, it names new docs. Their rows come from `OP_ROUTES` (the three skill bundle routes: `post_api_projects_project_id_skills_from_folder.md` for `install_skill_bundle`, and `get_api_projects_project_id_skills_skill_id_files.md` and `get_api_projects_project_id_skills_skill_id_files_path.md` for `export_skill_bundle`; per the Kiln component doc) or are added to `NOT_AVAILABLE` by hand (the smell check, detectability and the compare route: rule 3 sends the agent to its input).

## 8. The contract list

This is the full content of `app/mcp/kiln_mcp_server/skill_checks/harness_tuner_contract.json`. This document owns the content. The Kiln document [kiln_smells_skills_version.md](kiln_smells_skills_version.md) (section 8) owns the test and the shape: exactly the four keys `paths`, `ids`, `headings` and `front_matter_keys`; the four kinds `levers`, `techniques`, `playbooks` and `smells`; a `headings` key that is a file path or `kind:<kind>`; and a `front_matter_keys` key that is `kind:<kind>`. The content below uses this shape and no other key. `ids` name files by kind: `levers` in `references/levers/`, the three others in `references/improving_agents/<kind>/`. Path count for HT's start-up check: 71 ids and the 22 `paths` below are 93 files.

```
{
  "paths": [
    "references/improving_agents/index.md",
    "references/levers/index.md",
    "references/improving_agents/techniques/guide-skill-for-a-tool-set/sample-queries.md",
    "references/improving_agents/techniques/guide-skill-for-a-tool-set/schema-as-leaf-files.md",
    "references/improving_agents/techniques/guide-skill-for-a-tool-set/timestamps.md",
    "references/knowledge/memory.md",
    "references/knowledge/memory_formats/baseline_and_val_records.md",
    "references/knowledge/memory_formats/experiment_records.md",
    "references/knowledge/memory_formats/issue_records.md",
    "references/knowledge/memory_formats/open_questions.md",
    "references/knowledge/memory_formats/screening_and_probe_records.md",
    "references/knowledge/code_tool_authoring.md",
    "references/knowledge/code_tool_wrappers/actionable_errors.md", "references/knowledge/code_tool_wrappers/batch_with_errors.md",
    "references/knowledge/code_tool_wrappers/composite_resolve_fetch.md", "references/knowledge/code_tool_wrappers/context_on_tool_surface.md",
    "references/knowledge/code_tool_wrappers/normalize_inputs.md", "references/knowledge/code_tool_wrappers/paginate_all.md",
    "references/knowledge/code_tool_wrappers/preview_and_cap.md", "references/knowledge/code_tool_wrappers/readonly_guard.md",
    "references/knowledge/train_val_test.md",
    "references/knowledge/model_create_configs.md"
  ],
  "ids": {
    "levers": ["model", "new_tool", "output_mode", "params", "prompt", "skill", "tool_config"],
    "techniques": [
      "add-the-missing-requirement", "answer-only-from-the-source", "attach-the-knowledge-source",
      "cap-and-preview-wrapper", "consolidate-tools", "decision-model-for-a-classifier",
      "decline-rules-paragraph", "directive-in-the-tool-response", "document-into-a-skill",
      "errors-the-agent-can-act-on", "faster-provider-for-the-same-model",
      "guard-tool-calls-at-the-boundary", "guide-skill-for-a-tool-set", "long-prompt-into-a-skill",
      "model-swap-inside-a-class", "new-tool-description", "normalize-inputs-wrapper",
      "one-general-rule-per-edit", "policy-as-step-by-step-procedures", "prune-one-group-at-a-time",
      "remove-or-scope-tools", "rewrite-an-inherited-skill", "roll-up-tool", "skill-into-the-prompt",
      "state-the-output-contract", "structure-a-long-prompt", "thinking-level-ladder"
    ],
    "playbooks": [
      "answers-not-grounded", "change-the-surface-not-the-words", "cheaper-or-faster",
      "dealing-with-a-noisy-eval", "dealing-with-a-saturated-eval", "dealing-with-a-wrong-eval",
      "dealing-with-an-eval-near-zero", "dealing-with-train-wins-rejected-at-val",
      "failure-at-a-tool-call", "fit-the-tool-layer-to-the-agent", "know-the-agent-before-you-plan",
      "lost-in-long-instructions", "malformed-tool-calls", "missing-context-the-agent-could-be-given",
      "ordering-work", "output-contract-not-met", "requirement-missing-from-the-prompt",
      "skill-is-not-read", "spending-the-budget", "working-inside-restrictions",
      "wrong-scope-or-refusal", "wrong-tool-chosen"
    ],
    "smells": [
      "document-behind-a-lookup-tool", "faulty-inherited-skill", "fixed-call-chain",
      "general-query-tool-without-a-guide", "old-model", "one-file-skill-with-many-topics",
      "skill-too-small-to-earn-its-place", "too-many-tools", "tool-results-flood-the-context",
      "tool-search", "tools-on-a-live-server", "unnecessary-tools", "very-long-prompt",
      "very-long-skill-description", "very-long-tool-description"
    ]
  },
  "headings": {
    "references/improving_agents/index.md": [
      "How to read these documents", "Smells", "Goals", "Order of work", "Failure patterns",
      "Eval problems", "Design", "Techniques"
    ],
    "references/knowledge/memory.md": ["Write discipline", "Tags"],
    "references/knowledge/code_tool_authoring.md": ["Wrapper templates", "The allowlist rule"],
    "references/knowledge/model_create_configs.md": ["Key Parameters", "Kiln Name Validation"],
    "kind:levers": ["How to change it", "Limits"],
    "kind:techniques": ["How", "Check that it took effect"],
    "kind:playbooks": ["Situation"],
    "kind:smells": ["How to recognise it", "How to confirm it", "What it blocks", "Remedies"]
  },
  "front_matter_keys": {
    "kind:smells": ["title"]
  }
}
```

Every entry was checked on the fresh copy: each path exists, the id sets equal the folders (7, 27, 22 and 15 files), each kind heading is in every file of its kind, and every smell file has `title`. One entry is added at pre-flight: the path of the costing file, when it is found (5.2; architecture ruling 22).

**The Smells table.** `smell_ids` (section 3) needs each row of the "Smells" table of the index to have the backticked path of the smell file in its first cell. The four keys cannot hold this. So Kiln's contract test has one fixed check more: each id of `ids.smells` is in that table, written as `` `references/improving_agents/smells/<id>.md` `` (architecture ruling 14; per the Kiln component doc, which reads the table by the rule of `smell_ids`). HT guards the same thing at start-up: the check of the sibling document (section 4) runs `smell_ids` on the index and stops when it finds no id.

HT keeps the same list as a constant, `KILN_SKILL_PATHS` in `contract.py`, for its start-up check. New HT test `test_every_kiln_path_in_agent_text_is_in_the_contract`: every string that matches ``references/(improving_agents|levers|knowledge)/[^`\s)]+\.md`` in the role skills, their reference files and the prompt templates is in `KILN_SKILL_PATHS`, or is a `<id>` pattern of an id folder.

## 9. Tests

Existing tests, with collected counts at `b49f159` (3,965 in all):

| File (tests) | Change in steps 10 and 11 |
|---|---|
| `tests/test_baseline_review.py` (55) | Stays. `known_smells` comes from `FakeSkillReader` (`:98-99`); the patch of `_smell_titles` (`:464`) and the `KnowledgeError` cases (`:560-577`) use `FakeSkillReader(fail=…)` |
| `tests/test_smells.py` (44) | The tests that patch `load` (`:536-594`) use `FakeSkillReader`. The detector tests change in the sibling document |
| `tests/test_agent_templates.py` (73) | The 6 `kiln-api` deep-link tests (`:1221-1361`) go. `test_planner_skill_names_the_lever_attempts_input_and_the_knowledge` (`:1511-1529`) asserts the entry file name and no longer reads `levers/new_tool.md`. The `playbook` case of `test_the_val_rejection_readers_quote_every_reason_code_writes` goes; the `planner` case stays. The exception for the code tool skill in `test_no_loop_doc_or_prompt_tells_an_agent_to_call_the_generic_kiln_tool` goes. `GATEWAY_RULE` and its tests do not change |
| `tests/test_gateway.py` (89) | Gains the tests below. No test goes in these steps |
| `tests/test_dispatch_claude_cli.py` (124), `…_codex_cli.py` (39), `…_opencode_cli.py` (40) | A test that pins a role's exact tool list gains `kiln_skill` |
| `tests/test_docs.py` (55) | `resolve_link` (`:33`) moves to a helper in the test file. Done with the removal of `knowledge/` |
| `tests/test_knowledge.py` (108), `tests/test_knowledge_checks.py` (103) | Go with the copy and with `knowledge/`, last (sibling document). Until then they pass unchanged |

New tests:

| Test | Asserts |
|---|---|
| `tests/test_kiln_skill.py`: reader | With the two MCP functions patched: the text of a good result; `isError` becomes `KilnSkillError` with Kiln's text; an `ExceptionGroup` with a connect error, and HTTP 404, 421, each give the message of 1.3; a blank path is refused; a second read of one path makes no call; an error is not cached; the URL for a host with and without a trailing slash |
| `tests/test_kiln_skill.py`: parsers | `smell_ids` on a table with a header, a separator, marker lines and a second section; no id raises; `smell_title` with a plain title, a quoted title, no front matter, no title |
| `tests/test_gateway.py`: the tool | The text comes back unchanged, with quotes and newlines; no path is refused with "give a path"; an unknown path is an MCP error with Kiln's text; a text over 40,000 characters comes back as an `AnswerPart`; each of the 7 roles has the tool and the 3 others do not |
| `tests/test_smells.py` | `_smell_titles` reads the index once and each smell once for a run; a failed read logs `knowledge_unreadable`, returns `None` and is tried again |
| `tests/test_agent_templates.py` | The rendered prompt holds `KILN_SKILL_RULES` for the 7 roles only; the constant equals the pinned text of section 6; each role template names `references/knowledge-entry.md` and that file exists in the role's skill; each entry file starts with the fixed paragraph; no HT skill has a folder `references/knowledge/`, `references/levers/` or `references/improving_agents/`; no agent text names a removed skill; the three map tests of section 7; the lever table test of 4.2; the contract test of section 8 |

**Tests that bind HT's code to knowledge text** (architecture ruling 19). They cannot run offline after the switch, because the text is in Kiln. The functional spec (section 6) names three: the first three rows below. The code has more. The lever ids move into Kiln's contract test (section 8). Each of the others becomes a review item of the audit (sibling document, 8.2), and its test goes with the knowledge copy or loses the part that reads the copy:

| Test today | What it binds | After |
|---|---|---|
| `test_each_list_of_lever_ids_names_every_lever_document` (`tests/test_knowledge.py`) | The lever ids in HT's files against the lever documents | `ids.levers` of the contract list |
| `test_spending_the_budget_names_real_planner_input_fields` (`tests/test_knowledge.py`) | The playbook `spending-the-budget` against the fields of `schemas.BatchPlanInput` | Review item |
| `test_the_output_mode_lever_names_every_kiln_mode` (`tests/test_knowledge.py`) | The lever `output_mode`, "What it is", against Kiln's list of output modes | Review item |
| `test_the_output_mode_lever_is_what_the_code_does` (`tests/test_knowledge.py`) | The lever `output_mode` against what a screen and a probe can set | Review item |
| `test_the_output_contract_playbook_ranks_every_kiln_mode` (`tests/test_knowledge.py`) | The playbook `output-contract-not-met` against Kiln's list of output modes | Review item |
| The `playbook` case of `test_the_val_rejection_readers_quote_every_reason_code_writes` (`tests/test_agent_templates.py:310`) | The playbook `dealing-with-train-wins-rejected-at-val` against the reason lines that code writes. Kiln's playbook paraphrases the lines today, so the case would fail on Kiln's text | Review item. The `planner` case stays |
| The read of `levers/new_tool.md` in `test_planner_skill_names_the_lever_attempts_input_and_the_knowledge` (`tests/test_agent_templates.py:1511`) | The lever `new_tool` names the wrapper templates | Review item. The rest of the test stays |
| `test_rejection_stamp_is_in_the_memory_vocabulary`, `test_memory_skill_names_the_same_spend_slot_as_the_analysis_skill` (`tests/test_agent_templates.py:321`, `:458`) | The `memory` skill's text against the rejection stamp (`REJECTION_STAMP` of the test file) and against the analysis skill's `bundle cost` slot | Review item, against Kiln's `references/knowledge/memory.md` and its format files |

This table holds the tests that were found. Another test that reads removed text, and so cannot run after a removal, gets the same treatment: its part that tests HT's own files stays, and its part that reads Kiln's text becomes a review item.

## 10. Accepted limits

Each of these is settled. Nothing here waits for a decision.

1. **`memory.md` is written for a chat agent.** It tells its reader not to write a `hypothesis` record and to read the `baseline` record. Rules 5 and 6 of the shared block override both for a loop agent. Nothing in code enforces rule 6 for the `baseline` record (the gateway hides only `val`), as today.
2. **Kiln's knowledge links to chat procedure files**, for example `train_val_test.md` (18 links from the trees) and `run_an_experiment.md`. A loop agent can follow them: the whole skill is passed through (functional spec 5.1). The shared rules keep the role on its own procedure.
3. **Two kinds of path still look alike.** `references/knowledge-entry.md` is a file of the role's skill, on disk. `references/knowledge/…` is a path in Kiln's skill. The name, the fixed paragraph of section 4, the block of section 6 and one test keep them apart. If an agent mixes them up, the audit and the demo run show it.

## 11. Open points

1. **The path of the costing file is not known.** The fresh copy at `5522a7b9` has no port of `experiment-costing` (5.2). It is a pre-flight item (architecture ruling 22). Until then the planner's three pointers, one contract entry and the removal of HT's skill wait.

## 12. Not verified

- Everything in 1.6 against a real Kiln. The check that was made used a stand-in server (1.6).
- The `mcp` version that first has `streamable_http_client`.
- That Kiln's check keeps every skill file under 30,000 characters (architecture decision 4). `skill_checks/knowledge_schema.py` has limits for the knowledge kinds only (`MAX_CHARS`). The over-cap rule of section 2 does not depend on it.
- That the five memory format files hold every format that HT's `memory` skill stated. The files were listed and their headers read; they were not compared line by line.
- That the 8 template files are the same code as HT's 8 `.py` templates.
- The row count of the generated map beyond the 27 rows of section 7.
