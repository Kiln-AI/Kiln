---
status: complete
---

# Phase 4: Real-Provider Check

## Overview

Every agentic judge test so far scripts the model. This phase adds a paid test that runs an agentic judge end to end against real models on OpenRouter, to answer the two open questions from architecture §1 and §8: does structured output work when the judge also has tools, and do providers accept the trace tool schemas with their numeric bounds (`minimum`, `maximum`).

For each model, the test checks what architecture §7.8 asks for: the judge calls at least one trace tool before answering, and it returns schema-valid scores. It follows the repo's paid-test conventions: `@pytest.mark.paid` (skipped unless `--runpaid`), and `skip_if_missing_provider_keys` so a machine without `OPENROUTER_API_KEY` skips instead of failing.

If any model fails in one of the ways the plan names, implementation stops and the options go back to the user (a per-model structured output mode, a new model-list field, or a litellm upgrade).

The first run stopped there. Qwen and GLM read the trace correctly but wrote prose around their JSON, which the parser rejects. GPT-6 Luna looped, because OpenRouter makes OpenAI models fill every optional tool argument. The user chose to give trace tools judges a separate, scores-only final turn, built on the existing two-step chain of thought (steps 6 to 9). The GPT-6 Luna fix (`"strict": false` on tool definitions) is a separate adapter task.

## Steps

1. **Model set.** A small list of `(model_name)` entries on OpenRouter, cheap models from five vendor families, chosen to cover each structured output mode the judge sends alongside tools today:
   - `gpt_6_luna` (OpenAI, `json_schema`)
   - `claude_haiku_5_5` (Anthropic, `json_schema`)
   - `gemini_3_8_flash` (Google, `json_schema`)
   - `qwen_3p8_flash` (Qwen, `json_instruction_and_object`)
   - `glm_5_3_flash` (Z.ai, `json_instructions`)

   Each runs once per test run with the provider's default thinking level, as a user's judge would.

2. **Fixture trace.** A five-message support-agent trace: system prompt, a user asking where order A1234 is, an assistant `lookup_order` tool call, the tool's JSON result (status `delayed`, delivery `2026-10-31`), and a final assistant answer that contradicts it ("on schedule… tomorrow, October 18"). The trace overview the judge gets in its prompt previews the user message and the final answer but not the tool result, so the judge has to read the trace with a tool to compare them.

3. **Judge.** Built the way the app builds one: an in-memory `Task` and `Eval` (full trace, no spec, scores `Matches Order Data` pass/fail and `Overall Rating` five-star), `materialize_llm_judge_properties(..., trace_tools=True)` with one judge instruction, so the judge gets the default agentic prompt, the default system prompt and the latest toolset version. Run through `LlmJudgeEval(eval_config).evaluate(EvalTaskInput(final_message=..., trace=TRACE))`.

4. **Test** in `libs/core/kiln_ai/adapters/eval/test_v2_eval_llm_judge.py`, a new class `TestAgenticJudgeLive` after the scripted end-to-end class:

   ```python
   @pytest.mark.paid
   @pytest.mark.parametrize("model_name", AGENTIC_JUDGE_LIVE_MODELS)
   async def test_judge_reads_the_trace_then_scores(self, model_name: str): ...
   ```

   Assertions:
   - The tools the judge is given carry numeric bounds, so a pass means the provider accepted them.
   - Not skipped; `judge_trace` is present and ends with an assistant answer that has no tool calls.
   - At least one assistant message before that answer calls one of the five trace tools, and at least one tool result is not an error.
   - `scores` has exactly the eval's score keys; pass/fail is 0 or 1; five-star is a whole number from 1 to 5.
   - `matches_order_data` is a fail. The answer plainly contradicts the tool result, so a pass means the tool output didn't reach the judge intact.

5. **Run** the paid test once per model with `--runpaid`, mapping the environment's OpenRouter key to `OPENROUTER_API_KEY` on the command line only. Re-run only a model whose result is unclear.

6. **`chat/chat_formatter.py`:** `TwoMessageCotFormatter(..., wrap_user_input: bool = True)`. With `False`, the first turn's user message is the input as is, followed by the thinking instructions, never wrapped in `<user_input>` tags.

7. **`model_adapters/base_adapter.py`:** `AdapterConfig.separate_final_answer_turn: bool = False`. With it, `build_chat_formatter` returns `TwoMessageCotFormatter(system_message, input, cot_prompt, wrap_user_input=False)` on every model (reasoning models and tuned strategies included), and raises `ValueError` without thinking instructions. Runs continued from a prior trace keep `MultiturnFormatter`.

8. **`eval/v2_eval_llm_judge.py`:** with trace tools on, `_LlmJudgeTask` gets `thinking_instruction=_TRACE_TOOLS_THINKING_INSTRUCTION` (investigate with the trace tools, describe the decision for each score, the formatted version is asked for next), the run config uses `PromptGenerators.SIMPLE_CHAIN_OF_THOUGHT`, and `AdapterConfig(separate_final_answer_turn=True)`. Tools off: unchanged.

9. **Specs:** functional spec §6 and architecture §3.7 describe the two turns. In the live test, `gpt_6_luna` stays in the model list with a `TODO` naming its dependency on the strict tools fix, and isn't re-run.

## Tests

- `test_chat_formatter.py::test_two_message_cot_wraps_only_plain_inputs`: wrapped by default, unwrapped with `wrap_user_input=False` and for conversation history inputs.
- `test_base_adapter.py::test_build_chat_formatter_separate_final_answer_turn` (non-reasoning, reasoning, tuned single turn R1): first turn not final with the input unwrapped before the thinking instructions; final turn is `COT_FINAL_ANSWER_PROMPT`.
- `test_base_adapter.py::test_build_chat_formatter_separate_final_answer_turn_needs_thinking_instructions`.
- `test_v2_eval_llm_judge.py::test_only_trace_tools_judges_answer_in_a_separate_turn` (tools on and off): thinking instruction, prompt id and adapter flag.
- `test_v2_eval_llm_judge.py::TestLlmJudgeTraceToolsEndToEnd`: through the real adapter with a scripted reasoning model, the response format is skipped on both first-turn calls and sent on the final one, and the judge trace holds both turns in order.
- `TestAgenticJudgeLive::test_judge_reads_the_trace_then_scores[openrouter/<model>]` for each model in step 1: the judge calls a trace tool and gets a result before answering, returns schema-valid scores, and fails the contradicting answer. Skipped without `--runpaid` or without an OpenRouter key.
