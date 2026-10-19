---
status: complete
---

# Phase 1: Verify the RAG Punt

## Overview

Verification-only phase confirming that the RAG judge template + continuous scoring removal (commits `5efc626`, `74154c0`) landed cleanly on `scosman/evals_v2`. No code changes; this phase resolves one open question that feeds Phase 2 (Batch-1 item 1b).

## Verification Checklist

### 1. V1 scoring behavior identical to `main` (A0.1) -- PASS

**Evidence:**
- `git diff main -- libs/core/kiln_ai/adapters/eval/eval_utils/scoring_utils.py` shows the file is new on this branch (extracted from `g_eval.py`). The standalone `build_llm_as_judge_score` function at `scoring_utils.py:186-203` has identical logic to `main`'s `GEval.build_llm_as_judge_score` method: raises `ValueError` on non-dict output, raises on `None` token_score. No `strict` flag, no `allow_float` parameter, no float-leniency (`isinstance(value, (int, float))` early-return or `float()` fallback) -- all of which were RAG additions.
- `g_eval.py` diff vs `main` is purely a refactor: all scoring methods (`build_llm_as_judge_score`, `build_g_eval_score`, `g_eval_single_metric`, `raw_output_from_logprobs`, `token_search_range`, `rating_token_to_score`, `score_from_token_string`, `metric_offsets`) now delegate to the extracted standalone functions in `scoring_utils.py`. No logic changes -- only imports and return-delegation lines were added.
- `TOKEN_TO_SCORE_MAP` is identical (1-5, pass/fail/critical with the same float values).
- `GEval.__init__` still uses `allow_float_scores=False` at `g_eval.py:78`.
- No `strict` flag exists anywhere in `scoring_utils.py` (confirmed via grep).

### 2. V2 `llm_judge` is discrete (`allow_float_scores=False`), continuous scoring removed -- PASS

**Evidence:**
- `v2_eval_llm_judge.py:117-118`: `output_json_schema = BaseEval.build_score_schema(parent_eval, allow_float_scores=False)`.
- No `continuous`, `allow_float`, or `float_score` references exist in the file (grep returns only the single `allow_float_scores=False` line).
- No RAG template imports or continuous-scoring logic remain in `v2_eval_llm_judge.py` (183 total lines; `_filter_output_to_score_keys` removed; no `rag` or `template` references outside of Jinja2 prompt-template rendering which is unrelated).

### 3. No RAG references remain across `libs/`, `app/`, `specs/` -- PASS

**Evidence:**
- `grep -rn "rag_judge_template\|rag_template\|RagJudgeTemplate\|rag_judge" libs/ app/` returns no hits (zero output). The only `rag`-named files in `libs/` are the RAG feature itself (`rag_tools.py`, `rag_utils.py`, `adapters/rag/`, `datamodel/rag.py`) which are unrelated to the RAG *judge templates* for evals.
- `grep -rn "rag_judge_templates\|RagJudgeTemplate\|continuous_scoring\|continuous.scoring" libs/ --include="*.py"` returns zero hits.
- Source files `rag_judge_templates.py` and `test_rag_judge_templates.py` are deleted (only stale `.pyc` files remain in `__pycache__/`, which is gitignored).
- Specs references in `specs/projects/evals_v2/` are all properly annotated with "deferred from V2.0" / "punted" / "status: deferred" language, with forward-pointers to `/specs/projects/rag_templates/project_overview.md`:
  - `functional_spec.md:30` -- strikethrough + "Deferred from V2.0"
  - `implementation_plan.md:28` -- strikethrough + "RAG templates deferred from V2.0"
  - `components/29_rag_judge_templates.md:9` -- header banner: "Deferred from V2.0"
  - `components/00_overview.md:110,183` -- "Deferred from V2.0"
  - `components/21_type_llm_judge.md:210` -- V2.0 note on discrete scoring
  - `components/50_reference_data.md:134,144` -- RAG keys marked deferred
  - `components/80_extensibility_contract.md:158` -- deferred banner
  - `components/90_open_risks.md:182-192` -- section 2.11 documents the punt with bring-back plan
  - `phase_plans/phase_4.md:7,313` -- partial deferral noted

### 4. `specs/projects/rag_templates/project_overview.md` exists and records the removal SHA -- PASS

**Evidence:**
- File exists at `/Users/scosman/Dropbox/workspace/kiln_new/specs/projects/rag_templates/project_overview.md` (status: draft, 78 lines).
- Line 73: "The working implementation was removed in commit `5efc6265379fa9fff45b83e641896afb66325d14`"
- Records all removed files: `rag_judge_templates.py`, `test_rag_judge_templates.py`, changes to `v2_eval_llm_judge.py` and `scoring_utils.py`.
- Documents "Why pulled from V2.0" (5 reasons), "Complexities to solve before bringing them back" (continuous-score type, g-eval incompatibility, documentation), and design references.

### 5. OPEN QUESTION: Does `_filter_output_to_score_keys` still exist? -- NO, it was removed

**Definitive answer: `_filter_output_to_score_keys` does NOT exist in the codebase. It was removed with the RAG templates in commit `5efc626`.**

**Evidence:**
- `grep -rn "_filter_output_to_score_keys" libs/ --include="*.py"` returns zero hits.
- `grep -rn "_filter_output_to_score_keys" . --include="*.py" --include="*.md"` returns hits only in spec/plan `.md` files (the deep-cr-cleanup implementation plan and project overview discussing it, and the rag_templates bring-back plan at line 76).
- `v2_eval_llm_judge.py` is 183 lines total and contains no `filter` references of any kind.
- The removal commit `5efc626` message explicitly states: "Remove _filter_output_to_score_keys (RAG-specific rich JSON filtering)". The diff shows both the function definition (`-def _filter_output_to_score_keys(`) and its call site (`-        run_output = _filter_output_to_score_keys(run_output, score_names)`) being removed.

**Impact on Phase 2:** Batch-1 item 1b ("FIX `_filter_output_to_score_keys`: raise on no-match") is now **moot** -- the function no longer exists. Phase 2 should skip item 1b entirely. The implementation plan already anticipates this: "only if it survived the RAG removal."

## Gaps / Follow-ups

None. All 5 verification items passed. The only actionable finding is the Phase 2 scope adjustment: item 1b (`_filter_output_to_score_keys` fix) should be dropped since the function was removed with the RAG punt.
