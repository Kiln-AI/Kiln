---
status: complete
---

# Phase 5: Docs repo deprecation notice

## Overview

Mark the Prompt Optimizer as deprecated on the public docs site (`Kiln-AI/docs`, a GitBook git-synced repo) and point readers to Kiln Harness Tuner. The `automatic-prompt-optimizer` page stays at the same path so existing links resolve; every page that presents it as a current feature marks it deprecated without removing the link. Work happens in `~/dev/kiln_ws_1/docs` on branch `leonard/deprecate-prompt-optimizer`.

The repo is plain GitBook markdown: callouts use `{% hint style="..." %}`, navigation is `SUMMARY.md`, and page URLs come from file paths (not titles), so retitling nav entries doesn't break links. It has no build or lint tooling.

## Steps

1. **`docs/prompts/automatic-prompt-optimizer.md`:** insert a `{% hint style="danger" %}` block directly under the H1, above the existing enterprise-plan warning: "**Deprecated: the Prompt Optimizer has been retired.** Use [Kiln Harness Tuner](https://github.com/Kiln-AI/harness-tuner), which tunes prompts, tools, skills and model together." Leave the rest of the page unchanged.
2. **`SUMMARY.md`:** nav entry becomes `Automatic Prompt Optimizer (Deprecated)`; same path.
3. **`README.md`:** in the "Jump right in" cards, the optimizer card title becomes "Automatic Prompt Optimizer (Deprecated)" and its description "Retired. Use Kiln Harness Tuner instead."; card target unchanged.
4. **`docs/prompts.md`:**
   - frontmatter `description`: drop "our prompt optimizer".
   - first bullet: fix the mislabeled "Automatic Prompt Generator" link text to "Automatic Prompt Optimizer (Deprecated)", and replace its description with the retirement note plus Harness Tuner pointer.
   - the success hint: keep the first sentence; replace "Try our automatic prompt optimizer" with a Harness Tuner pointer that notes it replaces the deprecated optimizer (link kept).
5. **`docs/optimizers.md`:** the "Optimize Prompt" card text drops "using our automatic optimizers" (it links to `prompts.md`, not the optimizer page).
6. **`docs/fine-tuning/README.md`:** the "Before Fine-Tuning" hint points to Harness Tuner and mentions it replaces the deprecated Automatic Prompt Optimizer (link kept).
7. **`docs/tasks.md`:** in the single-turn vs multi-turn table, the link text becomes "Prompt Optimizer (Deprecated)".
8. **`docs/evals-and-specs/evaluations.md`:** both "automatic prompt optimizer" mentions (Training Dataset bullet and the Training and Validation Sets hint) are marked "(deprecated)"; links kept.
9. **Final check:** `git grep -n -i -E 'prompt.optimi|automatic-prompt-optimizer|gepa'` — every remaining hit is either on the deprecated page itself or carries a deprecated marker / Harness Tuner pointer.

## Tests

No test or build infrastructure in the docs repo. Verification is the step 9 grep plus a check that every edited `{% hint %}` block is balanced and every markdown link target still exists.
