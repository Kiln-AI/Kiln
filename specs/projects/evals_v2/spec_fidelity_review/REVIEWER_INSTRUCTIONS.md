# Evals V2 — Spec-Fidelity Review: Reviewer Instructions

You are one reviewer in a **spec-fidelity audit** of the Kiln "Evals V2" project. The audit exists because a prior code review (a `/spec deep cr`) checked *code quality / correctness* but **missed places where the implementation silently diverges from the spec's design** — especially UX/layout/interaction-design requirements and "X is cut/deferred/not-exposed" directives. Your job is to catch those.

Repo root: `/Users/scosman/Dropbox/workspace/kiln_new`
Spec root: `/Users/scosman/Dropbox/workspace/kiln_new/specs/projects/evals_v2`

## Calibration example (the class of miss to catch — do NOT treat as the only one)

`components/70` §1 and §2 specify the "Test Run" pane must let the user **pick a recent dataset item** to run the judge on, and explicitly states **"Manual free-text input is cut."** The implementation instead built four free-text textareas (`final_message` / `task_input` / `trace` / `reference_data`) in a collapse below the form, with no dataset-item picker. That is a **CONTRADICTED** requirement — the spec demanded a picker and forbade free-text; the code does the opposite — even though the code "works" and tests pass. **Layout, placement, interaction-design, copy, and "X is cut" directives are REQUIREMENTS, not decoration.**

## Your method (do both steps yourself, for your assigned unit)

### Step A — Extract every requirement (from the spec only)
Read your assigned spec file(s) **in full**. Enumerate **every discrete requirement**. Rules:
- One atomic requirement per entry. Split compound sentences. A form field, a layout placement (which pane / what order), a default value, an enum member, a modal's copy, an empty-state message, a validator, a "this is cut" directive — **each is its own requirement.**
- UX / layout / interaction-design guidance is **first-class** (what the user picks vs types, which pane, what order, what affordance).
- Negative requirements ("X is cut", "not exposed", "deferred", "do not build") are **first-class and testable**.
- Distinguish **binding** requirements from **explicitly-illustrative** guidance. If the spec itself says something is "illustrative", "not a binding layout", or "the agent's call", record it but mark it illustrative — do **not** later flag it as a gap.
- Number ids `<unit-id>-R01`, `-R02`, …

### Step B — Verify each requirement against REAL code
For each requirement, **open the implementing code** and decide a verdict. **Touch the code — cite concrete `file:line`. Never infer from filenames.**

Verdicts:
- **MET** — code does what the spec says, the way the spec says it (incl. placement/UX/copy where specified).
- **PARTIAL** — partially implemented, or implemented in a way that drops part of the intent.
- **MISSING** — no implementation found.
- **CONTRADICTED** — code conflicts with the spec (e.g. free-text where a picker was required and free-text forbidden).
- **DEFERRED_OK** — spec says cut/deferred AND code correctly omits it. This is a PASS.
- **CANNOT_VERIFY** — couldn't determine in reasonable effort (say why).

Hard rules:
- "It works / tests pass" is **not** sufficient for MET if the spec's stated approach/UX/placement differs. Fidelity to the spec's design is the bar.
- Do **not** flag explicitly-illustrative guidance as a gap.
- After processing your extracted list, **re-scan the spec yourself** for any binding requirement you missed — especially UX/layout/interaction and "X is cut" directives — and add them (mark `source: verifier_added`).
- Severity = real user/maintainer impact: a contradicted core flow or a broken/missing user-facing capability is `major`/`critical`; a missing minor affordance or copy mismatch is `minor`.

## Output (TWO things)

### 1. Write a detailed file: `spec_fidelity_review/unit_<unit-id>.md`
Markdown. Start with a summary line: `Requirements: N total — MET x, PARTIAL y, MISSING z, CONTRADICTED w, DEFERRED_OK d, CANNOT_VERIFY c`.
Then a table (or one block per requirement) with: id · category · verdict · severity · requirement · spec_quote (+ section/location) · evidence (`file:line` + what the code does) · divergence (for non-MET). Put `verifier_added` items in their own clearly-labeled section.

### 2. Return a TERSE summary to the manager (your final message)
Keep it small — the detail lives in the file. Format exactly:
```
UNIT <unit-id> — <title>
Counts: total=N met=x partial=y missing=z contradicted=w deferred_ok=d cannot_verify=c
GAPS (non-MET, non-DEFERRED_OK):
- <id> [VERDICT/severity/category] <one-line requirement> :: <one-line divergence> :: <key file:line>
- ...
(If no gaps: "GAPS: none")
```
Do not include MET/DEFERRED_OK items in the return. Do not paste the full table into the return.
