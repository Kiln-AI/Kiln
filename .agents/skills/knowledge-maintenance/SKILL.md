---
name: knowledge-maintenance
description: Add to, change and audit the knowledge of the Kiln skill (its levers, techniques, playbooks and smells under app/mcp/kiln_mcp_server/skill/references/levers/ and references/improving_agents/), and add entries to the knowledge backlog in app/mcp/knowledge_backlog.md. Use it for every change to those files - a new approach from a post, a lesson to record, a new document, an idea for later, a technique that went out of fashion, a fix ported from Kiln Harness Tuner - and for an audit. It gives the templates, the placement rules, the content rules and the commands that end each change.
---

# knowledge-maintenance

## 1. What this is

The knowledge is part of the Kiln skill, the skill that the Kiln MCP server
serves to coding agents (`app/mcp/kiln_mcp_server/skill/`). It holds what is
known about how to improve an agent built in Kiln. Any agent connected to the
Kiln MCP reads it, when a user asks it to improve a task.

It is two trees of the skill, with four component types. Each component is
one Markdown file, and its folder gives its type. Paths in this skill are
from the skill root, `app/mcp/kiln_mcp_server/skill/`:

| Type | Folder | What it is |
|---|---|---|
| Lever | `references/levers/` | One thing in a Kiln agent that can be changed, and how. Never when or why. |
| Technique | `references/improving_agents/techniques/` | One optimisation: when to use it, how, a cheap check, priors, confidence. |
| Playbook | `references/improving_agents/playbooks/` | How to solve one problem or reach one goal: an ordered list of things to try. |
| Smell | `references/improving_agents/smells/` | An issue in the design of the agent: how to recognise and confirm it, and links to its remedies. |

The file name without `.md` is the id. The two index files,
`references/levers/index.md` and `references/improving_agents/index.md`, hold
generated blocks. Code writes those blocks. A person or an agent never edits
them. The text around the blocks is hand-written.

The knowledge backlog, [`app/mcp/knowledge_backlog.md`](../../../app/mcp/knowledge_backlog.md),
lists the known gaps and the ideas that are not written yet. It is outside the
package, so no agent on the MCP reads it.

You, a coding agent that works on this repository, read this skill. Agents on
the MCP never read it: it is outside the package.

## 2. Before you start

1. Read the schema of the component type that you change:
   [references/schema.md](references/schema.md). It gives the front matter
   keys, the required sections and the size limits. This skill does not
   repeat them, so that the two cannot disagree.
2. Run the check, to see a clean state before you change anything:

   ```
   uv run python -m kiln_mcp_server.skill_checks check
   ```

   If it reports a problem before your change, tell the person. Do not mix
   a fix of an old problem into your change.

## 3. Choose the request

| The person asks | Procedure |
|---|---|
| "Read this post and add this approach" | 4.1 |
| "We learned a lesson, record this" | 4.2 |
| Add a technique, playbook, smell or lever | 4.3 |
| Add an idea or a gap for later | 4.4 |
| A technique went out of fashion | 4.5 |
| Port a fix from Kiln Harness Tuner | 4.6 |
| Audit | Section 10 |

If the request fits none of these, ask the person before you change a file.

## 4. The procedures

### 4.1 Add an approach from a source

1. Read the source.
2. State in one sentence what the approach changes in the agent.
3. Search the techniques for one that covers it. Read
   `references/improving_agents/index.md` and search
   `references/improving_agents/techniques/` for the key words.
4. If a technique covers it, extend that technique: add to `When to use`,
   `How` or `Priors`.
5. If none covers it, add a technique (4.3).
6. If the source is not public, apply section 8 to the text you add.
7. Decide if a playbook or a smell must link to it (section 5).
8. If the new text disagrees with existing text, stop (section 7).
9. Finish (section 9).

Reason: one approach with two documents gives two answers to one question.
The search in step 3 prevents a duplicate.

### 4.2 Record a lesson

1. Find the technique that the lesson is about.
2. Apply the approval rule (section 8). Show the person the exact text of
   the prior, and wait for the answer.
3. Add the prior to `Priors`.
4. Change `Confidence` only if this lesson changes it. Say why in the commit
   message.
5. Finish (section 9).

Reason: one case is one sample. It does not change the confidence alone,
unless it is the first case or it disagrees with the others.

### 4.3 Add a document

1. Copy the template of the type to the right folder, with the id as the
   file name:

   | Type | Template | Copy to |
   |---|---|---|
   | Lever | [templates/lever.md](templates/lever.md) | `references/levers/<id>.md` |
   | Technique | [templates/technique.md](templates/technique.md) | `references/improving_agents/techniques/<id>.md` |
   | Playbook | [templates/playbook.md](templates/playbook.md) | `references/improving_agents/playbooks/<id>.md` |
   | Smell | [templates/smell.md](templates/smell.md) | `references/improving_agents/smells/<id>.md` |

   The id is lower case, with words joined by `-`, of at most 60
   characters. A lever's id is the short name that experiments are recorded
   under, so it can also join words with `_` (`tool_config`, `new_tool`).
2. Fill every required part. Replace each `{{NAME}}` placeholder. Remove each
   HTML comment after you follow it. A link names an existing document by
   its full path from the skill root, for example
   `[roll-up tool](references/improving_agents/techniques/roll-up-tool.md)`.
   Never a bare file name, `./` or `../`.
3. Add the links in and out. A technique links its levers in `How`. A
   playbook links its techniques in `What to try, in order`. A smell links
   its remedies. Decide which playbook or smell must link to the new
   document (section 5). A playbook change needs the owners.
4. A playbook is a new problem or a new goal. If the problem has a
   playbook, the change goes in that playbook, not in a new one.
5. Finish (section 9). `build` adds the document's row to its index file.

Reason: a template has every required part, in order, so a check cannot
fail on a missing heading. A test holds each template to the schema.

### 4.4 Add an idea or a gap for later

Add an entry to [`app/mcp/knowledge_backlog.md`](../../../app/mcp/knowledge_backlog.md),
at the end of `Unranked`, in the fixed format that the top of that file
gives. Do not rank it. Run
`uv run python -m pytest app/mcp/kiln_mcp_server/skill_checks/test_knowledge_backlog.py`.

Reason: an entry needs no debate to be added. Its rank does, and the owners
decide the rank.

### 4.5 A technique went out of fashion

1. Set `status: dormant`, or narrow `When to use`.
2. Change each playbook and each smell that links to it. Use a search for
   its file name. A playbook change needs the owners (section 5).
3. Do not delete the file.
4. Finish (section 9).

A dormant technique can end with no links to it from other documents.
`build` lists it in the block `techniques-dormant` of
`references/improving_agents/index.md`, so it stays reachable from
`SKILL.md`, and it is not suggested. Each other rule still applies: a
playbook that loses its last step, or a smell that loses its last remedy,
fails the check.

Reason: a dormant technique stays in the system, so a reader can see that it
was tried and why it is not suggested. A deleted file loses that history.

### 4.6 Port a fix from Kiln Harness Tuner

Kiln's copy of the knowledge is the source of truth. Kiln Harness Tuner keeps
a duplicate for a short time, in
`src/kiln_harness_tuner/agent_files/skills/kiln-harness-tuner-knowledge/` of
its repository. A fix made there is ported here by hand. A fix made first in
Kiln's copy is not ported back.

The port was last brought up to date with Kiln Harness Tuner at commit
`b49f1594620862876d1e515cdda2f2deff018e95`.

1. Diff that folder of Kiln Harness Tuner from the recorded commit to its
   head.
2. Port each change by hand, with the same rewrites as the first port:
   links become full paths from the skill root; a gateway operation becomes
   the path of its endpoint doc under `references/knowledge/api_docs/`; a
   role of the tuner becomes "you"; a word of the tuner's loop becomes the
   general word ("arm" becomes "candidate" or "experiment", "the val gate"
   becomes "the confirmation on val", "a probe" becomes "a quick check").
   Change the words only, never what a rule requires. The check bans the
   tuner's words in the knowledge trees.
3. Finish (section 9).
4. Change the recorded commit above to the head that you ported.

## 5. Placement rules

Apply the first row that fits.

| The new material is | It goes in |
|---|---|
| A fact about what can be changed in a Kiln agent, or how | The lever document |
| A way to make one specific improvement | A technique |
| A reason to prefer one technique to another under a condition | `Alternatives` and `When not to use` of the techniques |
| An order of work for a goal or a situation | A playbook. Stop: playbooks are owned (below). |
| A problem to check for in the design of the agent | A smell, with its remedies |
| One case with a result | A prior on a technique |
| An idea with no content yet | The backlog |

Rules that go with the table:

- **New does not mean first.** Add a new technique to a playbook's order at
  the place that its condition gives. State the reason. Reason: a new item
  at the top of every list makes the order a record of age, not of value.
- **Playbooks are owned.** A change to a playbook's order needs the
  agreement of the owners. Propose the change, show it to the person and
  stop. A new technique, smell or lever needs no agreement. Reason:
  playbooks hold the opinions about order, and a small group keeps them
  consistent. The ownership is informal: there is no CODEOWNERS file.
- **Do not copy.** If the material is how-to text that a lever or another
  file of the skill already has, link to it. Reason: two copies go out of
  step, and a reader cannot tell which is correct.
- **Cost of maintenance.** Do not add a fact about one model, or about one
  point in time, that an agent learns from one failed call. Reason: such a
  fact goes out of date fast, and an agent finds it at almost no cost.
- **A smell is a property of the design.** A reason why one eval item
  failed is a failure pattern: it is a playbook of the kind `failure`, not a
  smell. Reason: a reader looks for each smell in the design, whether an
  eval passes or fails.

## 6. Content rules

These rules apply to every document of the two knowledge trees. A test
checks the structure. It cannot check these rules, so you apply them, and the
audit (section 10) looks for each one.

1. **Documents are ideas to try.** Do not write a rule of the form "you
   must do X". Say what to try, in what order, and under which conditions.
   The reader fits each suggestion to its agent: it knows more about that
   agent than the document does. A measurement on the user's agent outranks
   a document only when it is clearly past the noise. The exception is the
   safety and integrity rules of the lever documents (for example: never
   attach a tool that can reach the Kiln server). They are hard limits that
   no measurement overrides. Reason: what works varies from agent to agent,
   and a rule that overrides a clear result makes the reader ignore its own
   evidence. The hand-written part of `references/improving_agents/index.md`
   says this to the readers.
2. **State conditions, not defaults.** Each recommendation states the
   condition under which it holds. Reason: the research found a measured
   case where each "almost always" claim loses.
3. **State confidence.** Say how sure we are and on what basis. Reason: a
   reader must be able to tell an idea that one person proposed from a
   result seen many times.
4. **Date the guidance.** Set `reviewed` to the date of your review. Reason:
   the field changes each month, and a reader must know how old the text is.
5. **The cost of learning against the cost of maintenance.** Save a lesson
   that is expensive to learn. Leave out a lesson that an agent learns from
   one failed call. Be careful with a fact about one model or one date.
   Reason: a large base of facts is hard to maintain, and a stale fact
   misleads.
6. **Nothing measured on a user's project or on a demo project.** No
   measurement, lever advice or lesson from a user's own project or from a
   demo project. Reason: an agent that reads the answer invalidates the
   measurement that it is asked to make.
7. **General knowledge and other projects are allowed.** Field knowledge,
   public sources, our own synthetic experiments and anonymised cases from
   other projects can go in, under the approval rule (section 8). Reason:
   this is the knowledge that makes an agent's ideas better.
8. **Simplified Technical English** (ASD-STE100) in the two knowledge trees:
   short sentences, one idea each, no metaphor. Reason: the readers are
   models of many sizes, and simple text is read correctly more often. The
   rest of the skill has no language rule.
9. **Do not copy how-to material.** Link to the lever or to the file of the
   skill that has it. Reason: a copy goes out of step with its source.
10. **The split rule has one home.** Only
    `references/knowledge/train_val_test.md` states the rule for the train,
    val and test splits. A document that uses split wording names that path.
    No document selects, compares or keeps a candidate on the test split.

## 7. Conflicts

When the new material disagrees with existing guidance, stop. Do not choose.
Give the person three things:

1. the existing text, with its file and line;
2. the new text;
3. the two choices:
   - **Deprecate the old.** The old technique becomes `dormant`, or its
     `When to use` is narrowed.
   - **State when to use each.** Both stay. The `Alternatives` of each one
     names the other, with the condition.

Write the decision into the documents, in `Alternatives` or
`When not to use`, so that the next reader sees it.

Never delete an older approach, and never rewrite it to make room for a new
one.

Reason: a conflict is a decision about what the system believes. The person
owns that decision. A silent rewrite loses the old guidance and the reason
for the change.

## 8. Priors and approval

A prior is one real case in which a technique was used. It is one sample,
not a universal lesson, and its text says so.

The approval rule applies to a prior, and to any other text that you take
from a case that is not public: a step in `How`, a condition in
`When to use`, a case study.

- A prior never names a client, and never holds client data. The same is
  true for any text from a case that is not public.
- **Before the text is committed, a person approves it**, unless it is
  clearly public information: a published paper or post, with its link.
  Show the person the exact text and ask. Do not commit first and ask at
  review. Reason: a result can be sensitive when no entity is named, and a
  pull request review comes after the text is in the history.
- Never add a prior from a user's project or from a demo project (content
  rule 6).
- Before you write a number from a public source, open the source and check
  the number. Correct or drop a line whose numbers do not match.
- The form of a prior is in the `Priors` comment of
  [templates/technique.md](templates/technique.md). Its `Source:` is
  `public`, `own experiment` or `anonymised`. A test checks that value.
- A prior that is about a problem or an order of work, not one technique,
  goes on the playbook. A playbook has no `Priors` section in its
  template: add `## Priors` after `## Budget`, in the same form. The same
  test checks it.

## 9. Finish every change

Run these commands from the repository root, in order:

```
uv run python -m kiln_mcp_server.skill_checks build
uv run python -m pytest app/mcp
uv run ruff check
uv run ruff format --check
```

`build` rewrites the generated blocks of the index files and then runs every
check of the skill: the tree check (paths, reachability from `SKILL.md`,
banned words) and the knowledge check. To check without a rewrite, run
`uv run python -m kiln_mcp_server.skill_checks check`.

A change is not done while a check fails. Do not edit a generated block by
hand: change the documents and run `build`. Reason: a hand edit makes the
index disagree with the files, and the next `build` removes it.

## 10. Audit

The audit covers what a test cannot. It changes nothing. It returns a list.

For each document, report each of these, with the file and the line:

- a rule of the form "you must" (content rule 1), other than a hard limit
  of a lever document;
- a recommendation with no condition (content rule 2);
- a `Confidence` section that states no basis;
- a `reviewed` date older than six months;
- a lever document that says when to use the lever;
- how-to text copied from a lever or another file of the skill;
- a fact about one model or one date that an agent can learn cheaply;
- a prior that could identify a client;
- a playbook that repeats how to recognise its smell.

Run `uv run python -m kiln_mcp_server.skill_checks check` too, and add its
problems to the list.

Reason: a person decides what to fix. An audit that edits files mixes many
decisions into one change.
