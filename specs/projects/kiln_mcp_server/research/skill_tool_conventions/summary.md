# Skill tool conventions: what `kiln_skill` should copy

Research date: 2026-11-20. Versions read: Claude Code 2.1.329 (installed binary, its docs, and one live run), OpenCode `v1` branch at `c618499` (npm `opencode-ai` 1.19.6) and `dev` branch at `3bc82a1` (the v2 rewrite), OpenAI Codex `main` at `1c0c806`, the Agent Skills spec repo at `83021e2`, `anthropics/skills` at `e4bb5d9`, MCP SEP-2640 (Final) and the `ext-skills` repo, `mcp` 2.3.0 and `fastmcp` 4.2.3 from PyPI.

Network note: `agentskills.io`, `opencode.ai` and `developers.openai.com` are blocked by this session's proxy. Those pages were read through a search and fetch service, and checked against the GitHub sources where a source exists.

## Answer

No coding agent has a skill tool that takes a file path. Claude Code's tool is `Skill(skill, args?)` and OpenCode's is `skill(name)` (`skill(id)` in v2). Both return only the `SKILL.md` body and the skill's base directory (OpenCode adds a sample of up to ten file paths). The model then reads reference files with its ordinary file tool, by joining that base directory and the relative path written in `SKILL.md`. Codex has no tool for local skills at all: it lists each skill with a file path, and the model reads it with the shell. So "Claude Code's API with a `kiln_` prefix" gives the tool name and the first call, and nothing for reference files. The file argument is our own addition. The closest precedents for it are Codex's `skills.read(package, resource?)` for skills that are not on disk, Kiln's own `skill(name, resource?)`, and Shopify's MCP tool `use_skill(name?, path?)`. The hosts do not agree on the skill-name argument (`skill`, `name`, `id`, `package`), so there is no standard name to keep. They do agree on three things: one call returns the `SKILL.md` body, the body names files by a path relative to the skill root, and the host adds one sentence that says how to turn such a path into a read. `kiln_skill` should copy those three things.

There is also a real standard for "skill served by an MCP server": the MCP Skills extension (SEP-2640, Final since 2026-09-13). It serves the skill's files as `skill://` resources. Claude Code 2.1.329 contains client code for it, but in a live test it did not use it. No other coding agent consumes it yet. The tool is the right primary design today. The skill tree should be a valid Agent Skill, so that it can also be served through the extension later with no change to the content.

## Recommendation

**Tool name:** `kiln_skill`. Do not use the bare name `skill`. It is the name of the native skill tool in OpenCode and in Kiln's own agent runtime, and Kiln's runtime rejects a second tool with that name (`base_adapter.py`). Clients add their own prefix: the live run showed `mcp__kiln__kiln_skill` in Claude Code, and OpenCode builds `<server>_<tool>`.

**Arguments:** one optional string, `path`. No skill-name argument.

```json
{
  "name": "kiln_skill",
  "inputSchema": {
    "type": "object",
    "properties": {
      "path": {
        "type": "string",
        "description": "Optional. Leave unset on the first call: that returns the skill's instructions, which list the reference files. To read one of those files, set this to its path exactly as the instructions wrote it, relative to the skill root. Example: references/evals/overview.md. Do not guess paths."
      }
    },
    "required": []
  },
  "_meta": { "anthropic/alwaysLoad": true }
}
```

- Drop the skill-name argument. The tool serves one skill, so the argument has one valid value and can only be wrong. The Agent Skills client guide says to constrain a name argument to an enum of valid names. An enum of one carries no information.
- Do not fail a call that sends `skill`, `name` or `id` with the value `kiln`. Ignore it. A model that copies the native habit will send one of them.
- Call the file argument `path`. Reasons are in [Reasoning](#reasoning-for-the-conclusions).
- Accept these forms of `path` and treat them the same: `references/x.md`, `./references/x.md`, `skill://kiln/references/x.md`. Treat `SKILL.md` and an empty string as no path. Refuse absolute paths and any path that leaves the skill root.
- A path to a folder should return the folder's listing as a normal result. This matches `resources/directory/read` in SEP-2640. An unknown path stays an error that lists the nearest existing folder, as in the draft contract.

**Description wording pattern.** Copy the shape of Claude Code's `Skill` description: one imperative line, what the skill is, a "call this first" trigger rule, one bullet per argument, the slash-command sentence, and a "do not guess" rule. A native skill has its frontmatter `description` in the skills listing. Our tool has no listing, so the tool description must also carry that text. A pattern, not final wording:

```
Load the Kiln skill.

Kiln is an app for building, evaluating and improving AI agents and tasks. This skill is the instructions for it: what Kiln can do, how to use `call_kiln_api`, and guidance on evals and on improving an agent. When the user's request is about Kiln, call this tool first, before any other Kiln tool. Its instructions load into the conversation for you to follow. Users may also ask for it by name (`/kiln`, or "the Kiln skill"); that is a request to call this tool.

- No arguments: returns the skill's instructions. They list the reference files.
- `path`: returns one reference file. Copy the path exactly as the instructions wrote it, for example `references/evals/overview.md`.

Only paths the instructions list are valid. If the instructions are already in this conversation, do not load them again: call with `path` for the file you need.
```

Two limits matter for "the tool description is the prompt we inject into every agent":

- Claude Code defers MCP tool definitions by default (tool search). Its docs say: "Only tool names and server instructions load at session start". So in Claude Code the description is not in context until the model searches for the tool. Set `"anthropic/alwaysLoad": true` in the tool's `_meta`, and put the same trigger text in the MCP server `instructions` field.
- Claude Code cuts server instructions, and the description of an upfront tool, at 4,096 characters. Codex says to keep the first 512 characters of `instructions` self-contained. Put what Kiln is, and "call `kiln_skill` first", in the first 500 characters of both.

**Return format.** Plain text. No JSON envelope.

- No path: one header sentence, a blank line, then the `SKILL.md` body with the YAML frontmatter removed. Claude Code, OpenCode and Kiln's own tool all remove the frontmatter. The header copies the line Claude Code writes for a skill that an MCP server serves:

```
This skill is served by the `kiln_skill` tool. To read a file this skill references by a relative path, for example `references/evals/overview.md`, call `kiln_skill` with path "references/evals/overview.md". Paths are relative to the skill root.

<SKILL.md body>
```

- With a path: the file's text, unchanged.
- Unknown path: `isError: true`, and a message that names the bad path and lists the files in the nearest existing folder.

**How the content refers to files.** Write every reference as a path relative to the skill root, in backticks or as a Markdown link whose target is that same path: `references/evals/overview.md`. Use the full path in every file, also in files that are in a subfolder. Never write a bare filename, a path relative to the current file, or the text `kiln_skill(path=...)` in the content. The tool adds the access instruction (the header above and the description). The content stays a standard Agent Skill. `SKILL.md` should be a short map: one line per reference file, with its full path, what it contains, and when to read it. Add a test that every path written in any skill file resolves, and that every file is reachable from `SKILL.md`.

**MCP prompt.** Yes, add one. It costs a few lines and it gives a slash entry in Claude Code and OpenCode. It does not give a literal `/kiln`, and it gives nothing in Codex. Details are in [Reasoning](#reasoning-for-the-conclusions).

**Leave room for SEP-2640.** Give the skill the name `kiln` and a spec-valid frontmatter, and keep the tree self-contained. Then the same files can be served as `skill://kiln/SKILL.md` and `skill://kiln/references/...` when hosts start to consume the extension.

## The shapes, side by side

| Host | Tool the model calls | Arguments | What comes back | How reference files are read |
|---|---|---|---|---|
| Claude Code 2.1.329 | `Skill` | `skill` (string, required), `args` (string, optional) | Tool result `Launching skill: <name>`. The body arrives as a message that starts with `Base directory for this skill: <dir>` | Generic `Read` or `Bash` on base directory + relative path |
| OpenCode 1.19.x (`v1`) | `skill` | `name` (string, required) | `<skill_content name="…">`, the body, `Base directory for this skill: <dir>`, and up to 10 file paths in `<skill_files>` | Generic read tool |
| OpenCode v2 (`dev`) | `skill` | `id` (string, required) | Same text. Structured output `{directory, content}` | Generic read tool. It also accepts `skill://<id>/<file>` for skills that are not on disk |
| Codex, local skills | none | n/a | Skills are listed in the prompt with a file path | Shell |
| Codex, cloud and executor skills | `skills.read` | `package` (string, required), `resource` (string, optional), `cursor` (string, optional) | JSON `{resource, contents, skill_root?, next_cursor}` | The same tool, with `resource` set to the file's full `skill://` identifier |
| Agent Skills client guide (example only) | `activate_skill` | skill `name`, as an enum | Body in `<skill_content name="…">` with a `<skill_resources>` file list | File-read tool |
| SEP-2640 host sketch (example only) | `read_skill`, `read_resource` | `server`, `uri` | `SKILL.md` | `read_resource(server, uri)` |
| Kiln runtime | `skill` | `name` (string, required), `resource` (string, optional) | Body without frontmatter, or the file text | The same tool, with `resource` set to `references/…` or `assets/…` |
| Shopify MCP server | `use_skill` | `name` (optional), `path` (optional) | The list of skills, or `SKILL.md`, or one file | The same tool, with `path` |
| AWS MCP server | `aws___retrieve_skill` | skill name | "the full skill content including reference materials" | n/a |

## Evidence by question

### 1. Claude Code

**The tool.** The name is `Skill`. The schema below is the tool definition that Claude Code 2.1.329 sends to the model. It was read from a running session, and the two argument descriptions were also found as strings in the 2.1.329 binary.

```json
{
  "name": "Skill",
  "parameters": {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": false,
    "properties": {
      "skill": {
        "type": "string",
        "description": "The name of a skill from the available-skills list. Do not guess names."
      },
      "args": {
        "type": "string",
        "description": "Optional arguments for the skill"
      }
    },
    "required": ["skill"]
  }
}
```

`args` is not a file path. It is the text after a slash command (`/deploy staging`), which the skill body receives as `$ARGUMENTS`.

**The description text**, from the same session. A published copy (Piebald-AI, `tool-description-invoke-skill.md`, marked `ccVersion: 2.1.323`) has the same text with two variables.

```
Invoke a skill.

A skill is a packaged set of instructions the user or project has set up for a particular kind of task (deploy steps, a review checklist, a repo-specific workflow). Available skills appear in a listing from the system with one-line descriptions. When the task at hand is one a listed skill covers, call this tool first — the skill's instructions load into the turn for you to follow in place of your default approach; some skills instead run in a subagent and return the finished result. A skill that runs in the background returns only the agent's name — its result arrives later as a task notification, so don't wait on it or invoke it again in the meantime. Users may also ask for one by name (`/<name>`, or "slash command"); that's a request to invoke it.

- `skill`: exact name from the listing, no leading slash. Plugin skills use `plugin:skill`. Directory-scoped skills are listed with a path prefix (`apps/web:deploy`); when both scoped and unscoped variants of a name exist, pick the one whose directory contains the files you're working on (most specific wins; unscoped otherwise).
- `args`: optional arguments to pass through.

Only names from the listing (or that the user typed explicitly) are valid. Built-in CLI commands (`/help`, `/clear`, …) aren't skills. If a `<command-name>` block is already present this turn, the skill is loaded — follow it directly rather than calling again.
```

**How skills are listed.** A system message, not the tool description. In the session it reads `The following skills are available for use with the Skill tool:` and then one line for each skill: `- <name>: <description>`. The docs say the listing "always contains every skill name", that the combined `description` and `when_to_use` text is cut at 1,536 characters for each skill, and that the whole listing has a budget of 1% of the context window.

**What the tool returns.** The docs say: "the rendered `SKILL.md` content enters the conversation as a single message and stays there across later turns." The binary shows the details. The tool result is `Launching skill: <name>`. The message with the body is built as `Base directory for this skill: <skillRoot>`, a blank line, then the body. The frontmatter is not included. `${CLAUDE_SKILL_DIR}` in the body is replaced with the same directory. A second call for a skill whose content is unchanged adds a short "already loaded" note, not a second copy.

**Reference files.** They are read with the generic tools, on a path. The `Skill` tool does not read them. The docs tell authors to "Reference supporting files from `SKILL.md` so Claude knows what each file contains and when to load it", with this example: `For complete API details, see [reference.md](reference.md)`. The Agent SDK docs say that a skill's files "remain on disk and stay reachable through Read and Bash". On the Claude API and claude.ai there is no skill tool: "Claude reads `SKILL.md` from the filesystem using bash", and reads referenced files "using additional bash commands".

**A skill served by an MCP server.** The 2.1.329 binary has a second header for a skill that has no local directory. The text is exact; `ReadMcpResourceTool` and `ReadMcpResourceDirTool` are the values of the two variables in it:

```
This skill is served by MCP server "<server>" at <uri>. To read a supporting file this skill references by a relative path — for example "templates/invoice.md" — call ReadMcpResourceTool with server "<server>" and uri "<uri>/templates/invoice.md". Call ReadMcpResourceDirTool on "<uri>" or a subdirectory URI to list its contents.
```

This is Claude Code's own answer to our second question: keep relative paths in the content, and add one sentence with a worked example of the call. See question 6 for the state of this feature.

**Differences across versions**, from the history of the published copies:

- 2.0.20 (the first `Skill` tool): one argument, `command`. The tool description held the instructions and an `<available_skills>` block.
- 2.0.36: the argument is renamed to `skill`.
- 2.0.73: `args` is added.
- 2.1.23 and later: the listing moves out of the tool description into system messages.
- The Agent SDK uses the same `Skill` tool. Its `skills` option only filters which names the tool accepts.

Sources: [skills](https://code.claude.com/docs/en/skills.md), [tools reference](https://code.claude.com/docs/en/tools-reference.md), [Agent SDK skills](https://code.claude.com/docs/en/agent-sdk/skills.md), [Agent Skills overview](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview), [published copy of the tool description](https://github.com/Piebald-AI/claude-code-system-prompts/blob/main/system-prompts/tool-description-invoke-skill.md) (commits `9319b91`, `5fd0f76`, `085fb45`, `44566a0` for the history). The header strings and the result string are read from the binary. They are not in the docs.

### 2. OpenCode

**Released line, 1.19.x** (`v1` branch, `packages/opencode/src/tool/skill.ts`). The tool name is `skill`. The input is:

```
export const Parameters = Schema.Struct({
  name: Schema.String.annotate({ description: "The name of the skill from available_skills" }),
})
```

The description (`skill.txt`), exact:

```
Load a specialized skill when the task at hand matches one of the skills listed in the system prompt.

Use this tool to inject the skill's instructions and resources into current conversation. The output may contain detailed workflow guidance as well as references to scripts, files, etc in the same directory as the skill.

The skill name must match one of the skills listed in your system prompt.
```

The output, built in the same file:

```
<skill_content name="<name>">
# Skill: <name>

<SKILL.md body, trimmed>

Base directory for this skill: <dir>
Relative paths in this skill (e.g., scripts/, reference/) are relative to this base directory.
Note: file list is sampled.

<skill_files>
<file>/abs/path/one</file>
…up to 10 files, SKILL.md excluded
</skill_files>
</skill_content>
```

The listing is an `<available_skills>` block with `<name>`, `<description>` and `<location>` for each skill (`skill/index.ts`, `fmt`). The v1 docs page says the block is in the `skill` tool description. The current v1 source builds it in the system prompt. A skill is also a slash command (`/<name>`), with the same "Base directory" lines appended.

**v2** (`dev` branch, `packages/core/src/tool/plugin/skill.ts`). The name is still `skill`. The argument is renamed:

```
export const Input = Schema.Struct({
  id: Skill.ID.annotate({ description: "The ID of an available skill or a skill explicitly referenced by the user" }),
})
export const Output = Schema.Struct({ directory: Schema.String, content: Schema.String })
```

Description: "Load a specialized skill's instructions and resources into the current conversation when the task at hand matches its description." and "The skill ID must match an available skill or a skill explicitly referenced by the user." The text output is the same `<skill_content>` block. The listing gains an `<id>` element.

**Reference files.** The v2 docs say: "Supporting file contents are not loaded automatically. The agent reads them when the skill directs it to do so." and "Paths written inside the skill are relative to the directory containing `SKILL.md`." The read tool does the reading. For a skill that is not on disk (for example the built-in skills), v2 sets the base directory to `skill://<id>` and the file list to `skill://<id>/<file>`, and the read tool accepts those URIs (`tool/plugin/read.ts`). So v2 also keeps one loader tool and one generic reader. It does not add a file argument to the skill tool.

Sources: [v1 `skill.ts`](https://github.com/anomalyco/opencode/blob/v1/packages/opencode/src/tool/skill.ts), [v1 `skill.txt`](https://github.com/anomalyco/opencode/blob/v1/packages/opencode/src/tool/skill.txt), [v2 `skill.ts`](https://github.com/anomalyco/opencode/blob/dev/packages/core/src/tool/plugin/skill.ts), [v2 output format](https://github.com/anomalyco/opencode/blob/dev/packages/core/src/skill.ts), [docs](https://opencode.ai/docs/skills/). The path in the task brief, `sst/opencode` `packages/opencode/src/tool/skill.ts`, is now the `v1` branch of `anomalyco/opencode`.

### 3. OpenAI Codex CLI

**Local skills have no tool.** Codex puts a `## Skills` section in the context. Each entry is `- <name>: <description> (file: <path>)`. The instructions that follow (`codex-rs/ext/skills/src/catalog_prompt.rs`) tell the model to read the files itself:

> After deciding to use a skill, the main agent must expand the listed short `path` ... then open and read its `SKILL.md` completely before taking task actions.
>
> When `SKILL.md` references relative paths (e.g., `scripts/foo.py`), resolve them relative to the directory containing that expanded `SKILL.md` first, and only consider other paths if needed.
>
> If `SKILL.md` points to extra folders such as `references/`, use its routing instructions to identify the files required for the task.

The docs confirm it: "In Codex, the initial list also includes each skill's file path." A user starts a skill with `/skills` or with `$skill-name`. For a selected skill, Codex injects the content itself, as a `<skill>` block with `<name>` and `<path>` (inferred from `fragments.rs`).

**Skills that are not on the local disk have tools.** For "executor" and "cloud" skills, the same source defines a `skills` namespace with `skills.list` and `skills.read` (`codex-rs/ext/skills/src/tools/`). The arguments of `skills.read`:

```
struct ReadArgs {
    package: SkillLocator,     // schema type: string
    resource: Option<String>,
    cursor: Option<String>,
}
```

Its description starts: "Read one page from a skill. Pass its provided package directly; root aliases are resolved automatically. Omit resource to read SKILL.md; to read another file, use the same package and pass the file's complete skill:// identifier as resource." The response is JSON: `{resource, contents, skill_root?, next_cursor}`. The prompt adds: "do not treat `skill://` identifiers as filesystem paths."

This is the one native tool with the same two-step shape as `kiln_skill`: no file argument returns `SKILL.md`, a file argument returns that file. Two points limit how much weight it can carry. The tools are registered only when a per-step flag is on, and which released versions and products turn it on was not checked. The public docs describe only the file-path flow.

Sources: [`catalog_prompt.rs`](https://github.com/openai/codex/blob/main/codex-rs/ext/skills/src/catalog_prompt.rs), [`tools/read.rs`](https://github.com/openai/codex/blob/main/codex-rs/ext/skills/src/tools/read.rs), [`tools/list.rs`](https://github.com/openai/codex/blob/main/codex-rs/ext/skills/src/tools/list.rs), [`fragments.rs`](https://github.com/openai/codex/blob/main/codex-rs/ext/skills/src/fragments.rs), [docs](https://developers.openai.com/codex/skills).

### 4. The Agent Skills standard

**Frontmatter.** `name` is required: 1 to 64 characters, lowercase letters, digits and hyphens, no leading, trailing or double hyphen, and it "Must match the parent directory name". `description` is required: 1 to 1024 characters, what the skill does and when to use it. Optional fields: `license`, `compatibility` (up to 500 characters), `metadata` (string to string map), `allowed-tools` (experimental). The Claude Code docs say that claude.ai uploads and the Skills API reject any other field.

**Layout.** `SKILL.md` is required. `scripts/`, `references/` and `assets/` are optional, and they are "recommendations for organizing common types of content". Any other file or folder is allowed.

**Progressive disclosure.** Three levels: metadata (about 100 tokens, loaded at startup), instructions (the body, under 5000 tokens recommended, loaded on activation), resources (loaded when required). "Keep your main `SKILL.md` under 500 lines."

**File references.** The whole normative text is:

> When referencing other files in your skill, use relative paths from the skill root:
>
> ```
> See [the reference guide](references/REFERENCE.md) for details.
>
> Run the extraction script:
> scripts/extract.py
> ```
>
> Keep file references one level deep from `SKILL.md`. Avoid deeply nested reference chains.

So both a Markdown link and a bare path are in the spec's own example. Both are relative to the skill root, not to the file that contains them. Skills in `anthropics/skills` use all the forms: `see REFERENCE.md` (pdf), `[Python Guide](./reference/python_mcp_server.md)` (mcp-builder), and `` `references/schemas.md` `` in backticks (skill-creator).

**Tool interface.** The specification says nothing about one. The site has a guide for client authors, which is not normative. It describes two patterns: "File-read activation" with the standard file tool, and "Dedicated tool activation: Register a tool (e.g., `activate_skill`) that takes a skill name and returns the content." For the dedicated tool it advises: constrain the name to an enum; most implementations return the body without the frontmatter; wrap the content in `<skill_content name="…">`; list the bundled files but "not eagerly read them"; and state the skill directory in the result so that the catalog can omit it. It has no advice for a file argument, because it assumes the model has a file tool.

Sources: [specification](https://agentskills.io/specification) ([source](https://github.com/agentskills/agentskills/blob/main/docs/specification.mdx)), [client guide](https://github.com/agentskills/agentskills/blob/main/docs/client-implementation/adding-skills-support.mdx), [`anthropics/skills`](https://github.com/anthropics/skills).

### 5. Kiln's own skill tool

`libs/core/kiln_ai/tools/skill_tool.py`. One tool named `skill` serves every skill attached to a run config.

```json
{
  "name": "skill",
  "parameters": {
    "type": "object",
    "properties": {
      "name": {
        "type": "string",
        "description": "The name of the skill to load, exactly as listed in the system prompt."
      },
      "resource": {
        "type": "string",
        "description": "Optional. Leave unset on the first call: that returns the skill's instructions, which list its resource files if it has any. Set this only to a path those instructions listed, copied verbatim (paths start with references/ or assets/). Never guess a path; unlisted paths do not exist."
      }
    },
    "required": ["name"]
  }
}
```

The description: "Load an agent skill by name. Use this tool when a specialized skill may help solve the user's task. Skills use progressive disclosure: call skill(name) first to load the skill's instruction page. That page is the only place a skill's resource files are listed. If it points at a file you need, call skill(name, resource) and copy the path exactly as the instructions wrote it. Resource paths always start with references/ or assets/, but never guess or assemble one: a path the instructions do not list does not exist, and many skills ship no resource files at all."

- **Return.** `skill(name)` returns the `SKILL.md` body with the frontmatter removed (`Skill.body()`). `skill(name, resource)` returns the file text. Errors are plain strings with `is_error=True`: `Error: Skill '<x>' not found. Available skills: …`, `Error: Resource path must start with one of: references/, assets/`, `Error: Resource not found: <path>`, `Error: Path traversal is not allowed`.
- **Listing.** The system prompt gets a `# Skills` section (`prompt_builders.py`): "When a Skill is relevant, load it with `skill(name)` and follow its instructions. Load additional Skill resources only if needed with `skill(name, resource)`.", then `` - `<name>` `` and the description for each skill.
- **Reserved name.** `base_adapter.py` rejects a run config in which another tool is also named `skill`.

Harness-tuner's skills refer to this tool with the full call form. `kiln-task-setup/SKILL.md`: "At runtime the model reads them with `skill(name="<skill-name>", resource="references/…")`." Its authoring guide (`kiln-harness-tuner-experiment-build/references/skill-authoring.md`) gives the content rules that the tool depends on: the `SKILL.md` body is a map with, for each file, "its full `references/...` path and one line on what it covers and when to read it"; "Index resources by their full `references/...` path in the body too, never bare filenames"; and the description closes with "No other resource paths exist — never guess one."

Kiln's tool is already the shape we want, with a required skill name that `kiln_skill` does not need. Its two-step wording ("leave unset on the first call", "copied verbatim", "never guess") is worth reuse.

### 6. Precedent for a skill served over MCP

**The standard: the MCP Skills extension.** SEP-2640 is Final (merged 2026-09-13). Its identifier is `io.modelcontextprotocol/skills`. It serves each file of a skill as an MCP resource, by convention `skill://<skill-path>/<file-path>`, for example `skill://code-review/SKILL.md`. A server adds two methods, `skills/list` and `skills/get`, and may add `resources/directory/read`. Files are read with the standard `resources/read`. The skill format is delegated to agentskills.io. "Clients resolve relative references against the skill's root directory." The extension is written against base protocol revision 2026-07-28.

Why resources and not a tool or a new primitive, from the working group's rationale: "Skills are files; Resources exist to expose files." An earlier proposal for a first-class skill primitive (SEP-2076) was closed.

The SEP also gives a non-normative sketch of the tools a host shows the model: `read_skill(server, uri)` to load a skill, and a general `read_resource(server, uri)` for supporting files. "The host arranges for the model to know, when it loads an MCP-served `SKILL.md`, which server it came from and what its base URI is, for example by stating both in the `read_skill` tool result, so the model can resolve `references/GUIDE.md`".

**Who consumes it today.**

- Claude Code: not yet, in practice. The 2.1.329 binary contains the client (`skills/list`, `skills/get`, the header quoted in question 1, permission handling for "mcp_skill"). The changelog for 2.1.282 and 2.1.283 mentions "MCP servers' skills". But in a live test, 2.1.329 connected to a server that declared the extension, spoke protocol 2026-07-28, sent `server/discover`, `prompts/list`, `resources/list` and `tools/list`, and did not send `skills/list`. Its client capabilities did not declare the extension. The skill did not appear in the session's skills. The official client matrix has no mark for Claude Code in the Skills column. The public MCP docs page does not describe the feature.
- OpenCode: a community pull request, in progress (`ext-skills` implementations list).
- Codex: not listed. ChatGPT plugins import skills from an MCP server at submission time ("Partial").
- Hosts with full support are mostly inspectors and smaller agents: MCPJam, mcpc, fast-agent, Glean.
- Servers: Hugging Face, Cloudflare, Outline, n8n, Salesforce, Glean and others serve skills this way.
- SDKs: TypeScript SDK 2.4.0 and FastMCP 4.1.2 ship it. The Python SDK has it merged but not released: `mcp` 2.3.0 on PyPI has no skills module. FastMCP 4.2.3 served a test skill correctly in this research.

**Measured: resources alone are not discovered.** The Ansible AAP MCP server tested this (pull request 206, a proof of concept). With skills reachable only as resources, a fresh Claude Code session never read them: "8 tool calls, 0 resource calls". With the same catalog also published as tools, the model reached the skill "on call #2". Their conclusion: "Access was never the gap. Discovery is." They added a tool shim with `list_skills`, `get_skill` and `read_skill_file`, off by default.

**Other tool-shaped precedents.**

- Shopify's MCP server (tool definition read from a live connection on 2026-11-20): `use_skill`, with `name` ("A skill's frontmatter name. Omit to list the skills.") and `path` ("The path of one of the skill's resources, as listed. Omit to read SKILL.md."). Neither is required. This is the closest existing match to the draft `kiln_skill` contract.
- AWS MCP server: `aws___retrieve_skill` next to an API tool (`aws___call_aws`, now `aws___run_script`). This is the same two-tool design as `kiln_skill` plus `call_kiln_api`. The AWS docs add: "avoid referring to specific tool names in prompts, agent skills, or configurations."
- Before the SEP: `skilljack-mcp`, `skillsdotnet` (`load_skill` tool), `skillful-mcp` (`list_skills`, `use_skill`, `read_resource`), FastMCP's older resource-only provider.

**Would resources or prompts be a more standard fit than a tool?**

| | Claude Code | Codex | OpenCode |
|---|---|---|---|
| MCP tools | Yes. Definitions are deferred by default | Yes | Yes |
| MCP server `instructions` | Yes, loaded at session start, cut at 4,096 characters | Yes. "Keep the first 512 characters self-contained" | Yes (v2 docs) |
| MCP resources, model-readable | `ListMcpResourcesTool`, `ReadMcpResourceTool`, `ReadMcpResourceDirTool`; `@` mentions for the user | `list_mcp_resources`, `list_mcp_resource_templates`, `read_mcp_resource` (source) | `list_mcp_resources`, `read_mcp_resource` (v2 docs; not checked for v1) |
| MCP prompts as slash commands | Yes: listed as `/server:prompt (MCP)`, also typed as `/mcp__server__prompt` | No evidence of support: not in the docs' list of supported MCP features, and no prompt handler found in the source. Not searched exhaustively | Yes: `/server:prompt` (v1 source, v2 docs) |
| SEP-2640 skills | Code present, not active in 2.1.329 | No | Pull request open |

Resources are the standard carrier for the files, and all three agents can read them. But no agent looks at resources without a pointer, and only a SEP-2640 host turns them into a skill. Prompts are user-started: the model cannot call one, so a prompt cannot give progressive disclosure. A tool is the only surface that every agent shows to the model and that the model can call again for the next file. The tool is the right primary design. Resources (through SEP-2640) and a prompt are additions, not replacements.

The Claude Code check asked for in the brief is confirmed twice. The docs say: "Claude Code lists each MCP prompt as `/servername:promptname (MCP)`. Typing `/mcp__servername__promptname` also runs it." In the live run, a server named `kiln` with a prompt named `kiln` gave the entry `mcp__kiln__kiln` in the session's `slash_commands`, and the tool appeared as `mcp__kiln__kiln_skill`.

Sources: [SEP-2640](https://modelcontextprotocol.io/seps/2640-skills-extension), [extension overview](https://modelcontextprotocol.io/extensions/skills/overview), [`ext-skills`](https://github.com/modelcontextprotocol/ext-skills) (`docs/implementations.md`, `docs/rationale.md`, `docs/archive/related-work.md`), [client matrix](https://modelcontextprotocol.io/extensions/client-matrix), [Python SDK skills page](https://py.sdk.modelcontextprotocol.io/advanced/skills/), [AAP pull request 206](https://github.com/ansible/aap-mcp-server/pull/206), [AWS MCP tools](https://docs.aws.amazon.com/aws-mcp/latest/userguide/understanding-mcp-server-tools.html), [Claude Code MCP docs](https://code.claude.com/docs/en/mcp.md), [Claude Code changelog](https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md), [Codex MCP docs](https://developers.openai.com/codex/mcp), [OpenCode v1 `command/index.ts`](https://github.com/anomalyco/opencode/blob/v1/packages/opencode/src/command/index.ts), [Codex `mcp_resource_spec.rs`](https://github.com/openai/codex/blob/main/codex-rs/core/src/tools/handlers/mcp_resource_spec.rs).

## Reasoning for the conclusions

### The skill-name argument: drop it

- The native tools need the argument because they serve many skills. They name it four ways: `skill` (Claude Code), `name` (OpenCode v1, Kiln, Shopify, the Agent Skills guide), `id` (OpenCode v2), `package` (Codex). A model has no single habit to transfer, so nothing is lost when the argument is absent.
- A required argument with one valid value is a way to fail. The model must first learn the value (`kiln`? `kiln-skill`?), and the tool description is the only place to learn it.
- Shopify keeps `name` optional because, with no name, its tool lists many skills. We have nothing to list.
- If Kiln serves more than one skill later, add an optional `skill` argument then. A missing value keeps the meaning "the Kiln skill", so the change is compatible.

### The file argument: `path`

- In every native flow, the thing the model holds is a relative path, and the thing it does with it is pass a path to a file tool. The Agent Skills spec says "use relative paths from the skill root". Claude Code, OpenCode and Codex each tell the model that "relative paths" resolve against the skill's base directory. `path` is the word the model already has for this value.
- `resource` has a different meaning in two of the three target agents. In an MCP client it means an MCP resource: Claude Code has `ReadMcpResourceTool`, Codex has `read_mcp_resource`. A `resource` argument on an MCP tool invites a `skill://` URI, or a call to the wrong tool. In Codex's own `skills.read`, `resource` must be "the file's complete `skill://` identifier", not a relative path.
- Shopify's `use_skill` uses `path` for the same job. The draft contract already uses it.
- `file` has no precedent in any source read here.
- `resource` is Kiln's own word, and content ported from Kiln's skills may contain `skill(name, resource=…)`. That content must be rewritten for this tool in any case, because the `name` argument is gone. The server can also accept `resource` as an undocumented alias for `path`. That is cheap, and it covers a model that has learned Kiln's native form.

### How `SKILL.md` should point at reference files

- Native skills never write the access call into the content. The content has relative paths. The host adds the rule once: `Base directory for this skill:` (Claude Code, OpenCode), "resolve them relative to the directory containing that expanded `SKILL.md`" (Codex).
- When the files are not on disk, the hosts still do not change the content. They change the sentence. Claude Code's header for an MCP-served skill gives a full worked example of the call. Codex says "use the same access mechanism" and "use the same `package` and pass the file's complete `skill://` identifier as `resource`".
- So relative paths alone are not enough for us, and a rewrite of every link into `kiln_skill(path=…)` is not needed. The reliable native pattern is: plain root-relative paths in the content, plus one explicit sentence with an example, written by the tool. Put that sentence in the root result, where the model reads it at the moment it needs it, and in the description.
- Keep the access call out of the content for a second reason. The same tree can then be served through SEP-2640, or installed as files, where the call would be wrong. The AWS docs give the same advice for the same reason.
- Use full root-relative paths in every file. The spec resolves paths from the skill root, and a tool call has no "current directory". A link such as `[judges](judges.md)` inside `references/evals/overview.md` would fail.
- Kiln's own experience (the harness-tuner authoring guide) adds two rules that fit: the body is a map of full paths with one line each, and the text says that no other paths exist.

### An MCP prompt for a slash command: worth it, with limits

- Cost: one prompt registration. It can return the same text as `kiln_skill()` with no path, so there is one code path and no second copy to maintain. Claude Code says "Prompt results are injected directly into the conversation", so the skill loads with no tool call. Give it one optional argument for the user's request.
- Result in Claude Code: `/kiln:kiln (MCP)` in the `/` menu, and `/mcp__kiln__kiln` typed. Result in OpenCode: `/kiln:kiln`. The entry updates with the app, with no installed file.
- It is not a literal `/kiln`. A user who types `/kiln` should see the entry in the menu, because the menu filters on what is typed. That was not checked in an interactive session.
- It does nothing in Codex. Codex users start a skill with `$name` or `/skills`, and only for installed skills.
- So the prompt does not close the open decision in the project overview. It makes option one better in two of three agents. If a literal `/kiln` in every agent is a requirement, option two (a tiny installed `SKILL.md` that points at the tool) is still needed. That file would also give Codex its `$kiln` mention (inferred from the Codex docs).
- Keep the sentence "Users may also ask for it by name (`/kiln`…)" in the tool description in every case. It is Claude Code's own wording for the same situation, and it works in any agent.

### Serve the same files through SEP-2640 later

- It is the only standard that makes an MCP-served skill a native skill. A host that supports it lists the skill next to local skills and loads it through its own loader. In Claude Code that loader is the `Skill` tool. That is the product owner's goal in its exact form.
- The cost is low once the SDK supports it: the files are the same, and the server adds a manifest with a digest for each file. The project already plans to bump the `mcp` dependency.
- It is not usable as the only path today. No target agent consumes it by default, and resources without a host are not discovered (the AAP measurement).
- What to do now: make the tree a valid Agent Skill named `kiln`, keep all paths root-relative, and accept `skill://kiln/...` in `path`. What to decide later: when to turn the extension on, and whether `kiln_skill` should then stay for agents without it. The AAP server keeps both.

## Not verified

- Whether Claude Code's SEP-2640 client is behind a server-side flag, a setting, or a later release. The live test used `claude -p` with a stdio server and default settings.
- Whether `"anthropic/alwaysLoad": true` keeps `kiln_skill` upfront in every Claude Code configuration. The docs say the person who configures the server can still defer all its tools.
- Which released Codex versions register `skills.read`, and whether Codex can run an MCP prompt in any way.
- OpenCode and Codex were read from source and docs. Neither was run.
- Which reference style (Markdown link or backticked path) models follow more reliably through a tool. No source measures it. The recommendation follows the native examples and Kiln's own authoring guide. A small eval on the real skill tree would settle it.
