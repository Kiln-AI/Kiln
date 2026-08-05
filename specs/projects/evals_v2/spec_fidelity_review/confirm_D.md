# CLUSTER D — Copy/Label/UX Divergences: Skeptic Verification

## 27-R47 / 70a-R34: Trust modal copy diverges from spec

**Skeptic Verdict:** REFUTED_INTENTIONAL

**Corrected Verdict:** NOT a defect (spec is stale)

**Corrected Severity:** n/a

**Reasoning:** The spec requires trust-dialog copy including "never paste code from a stranger or the internet here" and explanation of FS/network access. The code instead reads: "This eval runs Python code on your machine. Only proceed if you trust eval code inside this project." This is a deliberate, documented user decision made post-spec:

1. Phase 12 (commit `6ac35ec4e`) removed all method/reassurance language per the user's "3.3 decision" as documented in `specs/projects/deep-cr-cleanup/implementation_plan.md` line 39.
2. Commit `8e0484121` ("fix(evals): shorten code_eval trust-dialog warning copy") further shortened the text.
3. Commit `89a69f249` ("fix(evals): drop secondary paragraph from code_eval trust dialog") removed the "review carefully / session-only" paragraph.
4. RUN_NOTES.md Morning Confirm List explicitly documents: "Per your 3.3 decision, all method/reassurance language was removed" and records the final user-approved text.

**Evidence:**
- `RUN_NOTES.md:9` (Morning Confirm List, Phase 12 entry with UPDATE)
- `implementation_plan.md:39` — "3.3 (trust-dialog wording — remove all method/reassurance language)"
- Commits: `6ac35ec4e`, `8e0484121`, `89a69f249`
- Code: `+page.svelte:714-722`

---

## 27-R49 / 70a-R24: "Python" label top-left of editor — code says "Score Function"

**Skeptic Verdict:** UPHELD

**Corrected Verdict:** MISSING (minor)

**Corrected Severity:** minor

**Reasoning:** The spec at `components/70_builder_and_onboarding.md:92` explicitly says: "CodeMirror 6 with @codemirror/lang-python — Python only, syntax highlighting, 'Python' label top-left of the box." The code uses "Score Function" as the label (introduced in Phase 6, commit `99f0c4332`). This was NOT addressed in any subsequent phase or user decision documented in RUN_NOTES. However, it survived Phase 12's code review without being flagged, and the description text at line 72 does say "Write a Python function that scores model outputs" — so "Python" is communicated via description if not via label.

This is a genuine minor divergence — the spec intended a language indicator on the editor chrome (like IDEs show), while the implementation chose a semantic/functional label instead. Neither RUN_NOTES nor any commit message documents this as an intentional override. It is minor polish that does not affect functionality.

**Evidence:**
- Spec: `components/70_builder_and_onboarding.md:92`
- Code: `code_eval_form.svelte:78-79` — label is "Score Function"
- Git: introduced in `99f0c4332` (Phase 6), never changed since
- No mention in RUN_NOTES or implementation_plan of intentional divergence

---

## 27-R52: Example button "Use this template" (spec) vs "Use This Example" (code)

**Skeptic Verdict:** UPHELD

**Corrected Verdict:** CONTRADICTED (minor)

**Corrected Severity:** minor

**Reasoning:** Spec at `components/70_builder_and_onboarding.md:97` and `:193` both say "Use this template" button. Code at `code_eval_form.svelte:128` says "Use This Example". Introduced in Phase 6 (`99f0c4332`), never changed. This survived Phase 12's review of the same file without being flagged, suggesting the reviewers considered it acceptable — but there is no explicit documented decision to change it. The semantic difference is negligible ("template" vs "example" for sample code snippets).

This is a genuine but trivial copy divergence. The spec should be updated to match code, or code updated to match spec — either direction is fine. Not a functional issue.

**Evidence:**
- Spec: `components/70_builder_and_onboarding.md:97,193` — "Use this template"
- Code: `code_eval_form.svelte:128` — "Use This Example"
- Git: `99f0c4332` (Phase 6 initial implementation, never amended)

---

## 27-R56 / 70a-R32: Save-Without-Testing modal copy differs

**Skeptic Verdict:** UPHELD

**Corrected Verdict:** CONTRADICTED (minor)

**Corrected Severity:** minor

**Reasoning:** Spec at `components/70_builder_and_onboarding.md:108` says: "I know, you're a great coder, but it never hurts to run it once." Code at `+page.svelte:743-745` says: "You haven't tested this judge yet. Running a quick test helps catch issues before saving. Are you sure you want to save without testing?"

The spec copy is whimsical/casual; the implementation copy is straightforward/informative. Introduced in Phase 6 (`99f0c4332`), never changed. The deep-cr-cleanup Phase 12 touched the same file (trust dialog) and did not flag the save modal copy — but this is not explicitly documented as an intentional override.

This is a genuine minor copy divergence. The implementation copy is arguably better UX (informative, no-nonsense). Spec should be updated to reflect actual copy.

**Evidence:**
- Spec: `components/70_builder_and_onboarding.md:108`
- Code: `+page.svelte:743-745`
- Git: `99f0c4332` (Phase 6), survived Phase 12 review without change

---

## 27-R57: Save-Without-Testing button "Save Without Testing" (spec) vs "Save Anyway" (code)

**Skeptic Verdict:** UPHELD

**Corrected Verdict:** CONTRADICTED (minor)

**Corrected Severity:** minor

**Reasoning:** Spec at `components/70_builder_and_onboarding.md:108` says button label should be "Save Without Testing". Code at `+page.svelte:734` says "Save Anyway". Introduced in Phase 6 (`99f0c4332`), never changed. Not documented as an intentional override.

"Save Anyway" is shorter and still communicates the same intent. This is a trivial label choice. The red styling (`isError: true`) is correctly applied per spec. The dialog title IS "Save Without Testing?" which covers the concept adequately.

**Evidence:**
- Spec: `components/70_builder_and_onboarding.md:108` — "red Save Without Testing / Cancel"
- Code: `+page.svelte:730-734` — "Cancel" + "Save Anyway" (with `isError: true`)
- Git: `99f0c4332` (Phase 6), unchanged since
