# The schema of the knowledge documents

The rules that `uv run python -m kiln_mcp_server.skill_checks check` holds
the knowledge trees to. The code is
`app/mcp/kiln_mcp_server/skill_checks/knowledge_schema.py`; when this file and
the code disagree, the code is right and this file is fixed.

Every path below is from the skill root, `app/mcp/kiln_mcp_server/skill/`.

## 1. Layout

| Type | Folder | Id pattern |
|---|---|---|
| Lever | `references/levers/` | lower-case words joined by `-` or `_` |
| Technique | `references/improving_agents/techniques/` | lower-case words joined by `-` |
| Playbook | `references/improving_agents/playbooks/` | lower-case words joined by `-` |
| Smell | `references/improving_agents/smells/` | lower-case words joined by `-` |

- A component is one Markdown file directly in its folder. Its id is the file
  name without `.md`, at most 60 characters.
- A sub-file is a Markdown file in a folder named after its component:
  `references/improving_agents/techniques/<id>/<name>.md`. Its component
  links it. A sub-file has no front matter.
- The two index files are `references/levers/index.md` (block `levers`) and
  `references/improving_agents/index.md` (blocks `smells`,
  `playbooks-goal`, `playbooks-order`, `playbooks-failure`, `playbooks-eval`,
  `playbooks-design`, `techniques`, `techniques-dormant`). They have no front
  matter. Each block sits between `<!-- BEGIN GENERATED: <name> -->` and
  `<!-- END GENERATED: <name> -->`, and `build` writes it. Each row names its
  document by its full path, so every document is reachable from `SKILL.md`
  through the index files.
- No other file belongs in the two trees, or directly in `references/`.

## 2. Links

A link to another file of the skill is a Markdown link whose target is the
full path from the skill root:
`[roll-up tool](references/improving_agents/techniques/roll-up-tool.md)`. A
link with `./`, `../` or a bare file name does not resolve. An anchor
(`#limits`) and an external URL are allowed.

## 3. Front matter

Each component starts with YAML front matter between `---` lines. Unknown
keys are an error. The body is Markdown with the required H2 sections of its
type, in the order given. Other H2 sections can follow the required ones.

### 3.1 Common keys

| Key | Type | Rule |
|---|---|---|
| `title` | string | 3 to 60 characters, one line |
| `description` | string | 40 to 200 characters, one line, no `\|`. It is the text of the index row, so it must let an agent decide whether to open the file. |
| `reviewed` | date | `YYYY-MM-DD`. Not after the UTC date plus one day, so a document dated "today" in any time zone passes. |

### 3.2 Task shapes

`applies_to` is the word `all`, or a list of one or more of:

| Shape | Meaning |
|---|---|
| `single_turn` | One request, one answer. Tool calls are allowed. |
| `multi_turn` | A conversation. |
| `structured_output` | The task has an output schema. |
| `free_text` | The task returns text. |
| `classifier` | The output is a small closed set of values. |
| `tools` | The agent has tools. |
| `no_tools` | The agent has no tools. |

A document applies to a task that has every shape in its list. `all` means
that the shape does not matter.

## 4. Lever (`references/levers/`)

The id of a lever document is the lever's name, for example
`references/levers/prompt.md`: the short name that experiments are recorded
under (`prompt`, `skill`, `tool_config`, `new_tool`, `params`).

Front matter, in addition to the common keys:

| Key | Type | Rule |
|---|---|---|
| `api_docs` | list of strings | Each is the full path of an endpoint doc under `references/knowledge/api_docs/`: not a catalogue (`*_api_list.md`) and not `api_index.md`. Can be empty. An endpoint that is blocked for agents has no doc, so a lever cannot name one. |

Required sections:

1. `## What it is`
2. `## How to change it`: the API calls, the rules of the object, and the
   steps.
3. `## Limits`
4. `## See also`: links to the existing how-to material. Can say "None."

Maximum size: 6,000 characters.

A lever document has no "when to use" text. A check cannot prove that, so
the audit covers it.

## 5. Technique (`references/improving_agents/techniques/`)

Front matter, in addition to the common keys:

| Key | Type | Rule |
|---|---|---|
| `status` | string | `active` or `dormant` |
| `levers` | list of strings | One or more ids of lever documents |
| `applies_to` | see 3.2 | |
| `cost` | string | `low`, `medium` or `high`: the cost to build and measure it, compared with a prompt edit |

Required sections:

1. `## When to use`
2. `## When not to use`
3. `## Alternatives`: each a link to another technique with its condition.
   Can say "None."
4. `## How`: the recipe. It links to each lever document it uses.
5. `## Check that it took effect`: a quick check, or a count in a few traces.
6. `## Budget`: when to leave it out, and when it is a good first step.
7. `## If it does not move the evals`: starts with one of the three
   phrases `Keep it.`, `It must move an eval.` or `It depends.`, then the
   conditions.
8. `## Priors`: a list of cases, or the line `None yet.`
9. `## Confidence`: text.

Maximum size: 12,000 characters. A sub-file: 20,000 characters.

Checks on the body:

- The `How` section links to each lever document in `levers`, and to no
  other lever document.
- Each link in `Alternatives` points to a technique.

An active technique has a row in the block `techniques`; a dormant one has a
row in the block `techniques-dormant`.

## 6. Playbook (`references/improving_agents/playbooks/`)

One playbook for each problem or goal. Its title names the problem.

Front matter, in addition to the common keys:

| Key | Type | Rule |
|---|---|---|
| `kind` | string | `goal`, `order`, `failure`, `eval` or `design`. It picks the index block. It changes no other rule. |
| `applies_to` | see 3.2 | |

| Kind | Meaning |
|---|---|
| `goal` | What the user wants |
| `order` | How to plan the work |
| `failure` | A class of failure seen in the traces of eval items |
| `eval` | A problem with an eval or with the measurement |
| `design` | The response to a smell that needs more than one technique |

Required sections:

1. `## Situation`: the goal, or how to recognise the problem. For the kind
   `failure`: what the trace shows, and where in the trace. A playbook that
   responds to a smell links to the smell here and does not repeat how to
   recognise it.
2. `## What to try, in order`: a numbered list. Each item links to a
   technique or a playbook and states its condition.
3. `## What not to do yet`
4. `## Budget`: how the order changes with the budget, or the line
   `The order does not change with the budget.`

A playbook can have an optional `## Priors` section after `## Budget`, in
the form of section 8.

Maximum size: 8,000 characters.

Checks on the body: `What to try, in order` has at least one link to a
technique or a playbook, and each link there points to one of those two
types.

## 7. Smell (`references/improving_agents/smells/`)

A smell document is a guide to recognise and diagnose one issue in the
design of an agent.

Front matter: the common keys and `applies_to` (see 3.2).

Required sections:

1. `## What it is`
2. `## How to recognise it`: the signs in the design, and the signs in how
   the agent runs.
3. `## How to confirm it`: what to check before it is reported, and what
   looks like this smell and is not.
4. `## What it blocks`: or the line `Nothing.`
5. `## Remedies`: a list. Each item links to a playbook or a technique and
   states its condition. This section holds links, not the fix.

Maximum size: 4,000 characters.

Checks: `Remedies` has at least one link, and each link there points to a
playbook or a technique.

## 8. Priors

A prior is one list item in the `Priors` section of a technique, or of a
playbook (section 6):

```
- **<shape of the agent, without a name>.** <what was tried>. <what happened>.
  Source: <public | own experiment | anonymised>. <date>.
```

The check requires that each item has a `Source:` with one of the three
values. Everything else about a prior is in section 8 of the maintenance
skill.

## 9. Other rules

- A `{{NAME}}` placeholder of a template, outside a fenced block, is an
  error in any document, its front matter included.
- The tree check of the whole skill also applies: every path resolves, every
  file is reachable from `SKILL.md`, and the knowledge trees use none of
  Kiln Harness Tuner's operation names, role names or loop words.
