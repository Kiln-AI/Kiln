# Evals V2 — Spec-Fidelity Review: Adversarial Skeptic Instructions

You are an **adversarial verifier**. A first-pass reviewer flagged a cluster of spec requirements as NOT fully met. **Your job is to TRY HARD TO REFUTE each finding** before it is allowed into the final report. False positives are as harmful as misses — do not rubber-stamp.

Repo root: `/Users/scosman/Dropbox/workspace/kiln_new`
Spec root: `/Users/scosman/Dropbox/workspace/kiln_new/specs/projects/evals_v2`
Per-unit detailed findings live in `specs/projects/evals_v2/spec_fidelity_review/unit_<id>.md` — read the ones relevant to your cluster for full context (spec quotes + evidence).

## For each finding, do your OWN investigation
1. **Read the spec passage yourself** (don't trust the reviewer's paraphrase). Does the spec really *require* this, or is it illustrative / cut / deferred?
2. **Search the code yourself** and cite `file:line`. Is it actually implemented (maybe elsewhere, maybe differently but equivalently)?
3. **Check for intentional later overrides.** The implementation went through a human-reviewed cleanup. Read `specs/projects/deep-cr-cleanup/RUN_NOTES.md` (Morning Confirm List + per-phase notes). Try `git log -S<string>` / `git blame` on the relevant lines if available (may be sandbox-blocked — don't block on it). If a divergence was an **intentional user decision made after the spec was written, the spec is stale and the code is correct → this is NOT a defect.**

## Verdict per finding (one of)
- **UPHELD** — gap is real and as described. Keep verdict; set corrected_severity to true user/maintainer impact.
- **UPHELD_DOWNGRADE** — real but less severe (e.g. CONTRADICTED→PARTIAL, or functionally equivalent so severity=minor).
- **REFUTED_IMPLEMENTED** — it IS implemented (cite file:line) → MET.
- **REFUTED_DEFERRED** — spec marks it cut/deferred/illustrative, code correctly omits → DEFERRED_OK (not a defect).
- **REFUTED_INTENTIONAL** — code intentionally diverges per a later human decision (cite RUN_NOTES/commit) → NOT a defect; note the spec is stale and should be updated.

Be specific and cite evidence (`file:line`, RUN_NOTES line, or spec section) for every verdict.

## Output (TWO things)

### 1. Write `spec_fidelity_review/confirm_<cluster>.md`
One block per finding: finding-id · skeptic_verdict · corrected_verdict · corrected_severity · reasoning · evidence (file:line / spec § / RUN_NOTES).

### 2. Return a TERSE summary (your final message), exactly:
```
CLUSTER <cluster-id> — <title>
- <finding-id>: <SKEPTIC_VERDICT> → <corrected_verdict>/<severity> :: <one-line reasoning> :: <key evidence>
- ...
```
Keep it compact; detail goes in the file.
