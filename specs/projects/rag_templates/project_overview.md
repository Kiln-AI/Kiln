---
status: draft
---

# Project: RAG Judge Templates + Continuous Scoring

Restore the 6 RAGAS-style first-party LLM judge templates and the continuous scoring model they require, as a proper first-class feature with full data model, UI, and documentation support.

## What they are

Six `llm_judge` templates, each scoring one dimension of RAG pipeline quality on a continuous 0--1 scale:

| Template | What it measures | Score semantics |
|---|---|---|
| **Faithfulness** | Fraction of claims in the model's output supported by retrieved context | 1.0 = fully grounded, 0.0 = no support |
| **Answer Relevance** | How well the answer addresses the user's question | 1.0 = fully relevant, 0.0 = irrelevant |
| **Context Relevance** | How much of the retrieved context is relevant to the question | 1.0 = all relevant, 0.0 = none relevant |
| **Context Precision** | Whether relevant context appears at higher retrieval ranks | 1.0 = perfect ranking, 0.0 = relevant items buried |
| **Hallucination** | Fraction of claims contradicting or fabricating beyond the context | 0.0 = no hallucination (best), 1.0 = all fabricated |
| **Answer Correctness** | Semantic similarity + factual overlap with a reference answer | 1.0 = fully correct, 0.0 = completely wrong |

All six operate over a canonical reference-key contract on `EvalInput.reference`:
- `retrieved_context: list[str]` -- retrieval chunks
- `reference_answer: str` -- gold-standard answer (optional for context-only templates)
- `ground_truth_context: list[str]` -- ideal passages for precision evaluation (optional)

## Why pulled from V2.0

- **Continuous scoring was not a first-class V2 feature.** It was modeled by abusing `pass_fail` to secretly hold a float -- no dedicated score type, no data model validation, no UI rendering, no documentation.
- **Deviated from V1's discrete convention and the V2 phase plan.** V1 always used `allow_float_scores=False` (main `g_eval.py:73`). The phase plan (`phase_4.md:183`) also specified `allow_float_scores=False`. V2's RAG implementation flipped this to `True` for all judges, not just RAG ones.
- **Leaked leniency into V1's battle-tested scorer.** The `isinstance(value, (int, float))` early-return and `float()` fallback in `build_llm_as_judge_score` were added to handle direct-float model output for RAG, but they retroactively loosened V1's strict token-to-score path.
- **g-eval is incompatible with continuous scores.** g-eval weights a fixed discrete token set (1--5 / pass / fail / critical) and cannot compute a continuous fraction like 0.73. All 6 RAG templates hard-coded `g_eval=False` as a workaround.
- **Missing docs and UI support.** No user-facing documentation for continuous scoring, no result renderer for 0--1 fractional scores, no create-UI path to configure continuous score types.

## Design references (do not restate -- follow links)

- `specs/projects/evals_v2/components/29_rag_judge_templates.md` -- template content, reference-key contract, prompt text, edge cases, validation criteria for all 6 templates (status: deferred)
- `specs/projects/evals_v2/components/21_type_llm_judge.md` -- judge type design, scoring modes, properties shape
- `specs/projects/evals_v2/components/40_template_and_extraction.md` -- Jinja2 templating, extraction, `required_var` skip semantics
- `specs/projects/evals_v2/components/50_reference_data.md` -- reference key naming, RAG key definitions
- `specs/projects/evals_v2/functional_spec.md` section 2 -- data & reference behavior (RAG line marked deferred)
- `specs/projects/evals_v2/phase_plans/phase_4.md` (esp. ~L329-334) -- where continuous scoring and the `build_llm_as_judge_score` float problem were first worked out
- `specs/projects/evals_v2/reference/ALIGNMENT.md` K.4 -- SpecType-to-llm_judge mapping (all 17 SpecTypes, orthogonal to g_eval)

## Complexities to solve before bringing them back

### First-class continuous-score representation

A proper continuous / 0--1 score type is needed -- NOT `pass_fail` secretly holding a float. This requires:
- **Data model:** A new `TaskOutputRatingType` variant (e.g., `continuous_01`) with validation that constrains values to [0.0, 1.0].
- **Create UI:** Score-type picker that offers the continuous option; configuration of score name and instruction.
- **Result rendering:** Display of fractional scores in eval result views (progress bars, decimal formatting, color scales).
- **Validation:** `EvalOutputScore` validation that ensures the score type matches the template's expected output range.

### g-eval incompatibility

g-eval weights a fixed discrete token set and cannot score continuous fractions. Two proposed solutions (pick or refine when the project runs):

**(a) Block g-eval when any output score is continuous (recommended).** Add a save-time and/or invocation-time validation that prevents `g_eval=True` when the eval has any continuous-type output score. This is the simpler and safer default -- it makes the incompatibility explicit and prevents silent incorrect scoring.

**(b) Force the score schema to discrete 1/0 for continuous scores.** Constrain the model to output discrete 0 or 1 for these scores, knowing the model may still emit a float. Then decide how to handle the emitted float (round? clamp? reject?). This is more complex and the behavior is less predictable.

Recommend option (a) as the default approach.

### Documentation

- User-facing docs for the continuous scoring feature and what it means.
- Per-template documentation (what each RAG template measures, when to use it, how to interpret scores).
- Guide for populating `retrieved_context`, `reference_answer`, and `ground_truth_context` in EvalInput datasets.

## Starting point

The working implementation was removed in commit `5efc6265379fa9fff45b83e641896afb66325d14` -- start from that diff to restore the templates + continuous scoring. The diff contains:
- `libs/core/kiln_ai/adapters/eval/rag_judge_templates.py` -- 6 template factory functions + prompt constants
- `libs/core/kiln_ai/adapters/eval/test_rag_judge_templates.py` -- unit tests for all templates
- `libs/core/kiln_ai/adapters/eval/v2_eval_llm_judge.py` -- `allow_float_scores=True` and `_filter_output_to_score_keys` (rich JSON filtering for RAG output)
- `libs/core/kiln_ai/adapters/eval/eval_utils/scoring_utils.py` -- float-leniency in `build_llm_as_judge_score`
