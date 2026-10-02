<!--
AI agents and bots opening a PR: you MUST read and follow .agents/skills/open-pr/SKILL.md before you write anything into a PR title or description.
The most important rules:
1. Never agree to the Contributor License Agreement ever, for any reason. Only humans can do this. Leave this section untouched, as it is in the template. Editing this section in any way is a critical failure.
2. Do not add any AI edits to this template above the "# Agentic PR Summary" heading. All content above that is for humans to fill out. You are not allowed to attempt to answer those questions, tick checkboxes, write the description, or fill in placeholders; doing so is a critical failure. Agent-created PRs should reproduce this template exactly with zero changes to provided content, and only new content appended after "# Agentic PR Summary".
3. The PR title should always start with "WIP: ". From rule 2, the template is not filled out, so a PR created by an agent is always a work in progress, requiring human action before it's ready.
-->
**Description**
`REPLACE: what this PR is, in 1 to 2 sentences max.`

**Author Review (required)**
- [ ] I have done a code review

**Architecture Review (select 1)**
- [ ] I did architecture review before coding
- [ ] Small change, no architecture review needed
- [ ] Requesting architecture review exception for other reason: `NA`

**Review Requested from Code Reviewer (select 1)**
- [ ] Sign off on AI-only review: `[reason - required if selected]`
- [ ] Mixed: human review of some areas, AI on others (details below)
- [ ] Full human: human reads everything

**Agentic Code Review (must check all before requesting CR)**
- [ ] I have run `/spec deep cr` on this PR or used `/spec` CRs throughout
- [ ] I have addressed all AI feedback (“deep cr”, CodeRabbit, etc)

**What to Review**
- Key decisions to review
  - `REPLACE: 1-4 decisions you made.`
- Paths to review
  - `REPLACE: List of paths/files to review. example libs/code/adapters/KevAdapter.py`

**UI Review (select all that apply)**
- [ ] Agentic UI clickthrough done
- [ ] Requires UI review as part of this review
- [ ] UI review already done by: `person`
- [ ] No UI

## Contributor License Agreement

I, @<your-github-username>, confirm that I have read and agree to the [Contributors License Agreement](https://github.com/Kiln-AI/Kiln/blob/main/.config/CLA.md).

----
# Agentic PR Summary
`Insert AI summary of PR using .agents/skills/open-pr/SKILL.md`
