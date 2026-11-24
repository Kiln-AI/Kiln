---
title: The output contract is not met
description: The output breaks its format - broken JSON or JSON that misses the task's schema, a closing block, a layout of free text, an escaping rule, or the form of a field.
reviewed: 2026-11-13
kind: failure
applies_to: all
---

# The output contract is not met

## Situation

The eval fails on the form of the output, not on its content. Look at the
end of the trace, in the final output of the agent, and at the errors of
the runs:

- the output is not valid JSON, or the JSON does not match the task's
  output schema (a stop on invalid output, or Kiln's error that the JSON
  does not meet the schema);
- a required block is missing, or it is not closed;
- the free text does not have the layout that the task requires;
- a character is not escaped as the task requires;
- a field holds a value in the wrong form (a date form, the empty case).

The content of the answer is often right. The first item is a failure of
the JSON shape, on a task with an output schema. The output mode of the
run config is its first suspect (the section "The output modes, ranked",
below). The other items are a format rule that nothing enforces, and a
prompt line is their first fix. A rule about the content of a field is a
rule of this second kind, also under a schema.

## What to try, in order

1. **A JSON shape failure, and the mode is not the model's default.** This
   can happen just after a model swap that kept the parent's mode. Set the
   default mode on a new run config:
   `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_run_configs.md`
   gives the mode, and
   `references/knowledge/api_docs/get_api_model_info_model_details.md` gives
   the default. On a run config with a tool or a skill, a tool-call default
   is refused: use the fallback that step 4 of the model lever gives. Read
   invalid output after a swap as a wrong mode first, not as a weaker model.
2. **A JSON shape failure under the model's default mode, and a stronger
   mode is in the ranking below.** On a run config with a tool or a skill,
   leave out the tool-call modes of rank 2: Kiln refuses them there. Screen
   the stronger mode in code: a screening candidate with an override of
   `structured_output_mode`. A quick check (`check`) with that override and
   `count: json_valid` answers first, in a minute, whether the outputs parse
   under it. It does not check the schema: a run that Kiln fails on the
   schema shows as a drive error. Read the drive errors in the evidence, not
   only the answer. When the agent calls tools, check `tool_calls` quickly
   under the new mode too. A mode change can move other items, and code
   treats it as a model-level swap. The screen measures those items against
   the baseline: read its quality line, not only the validity count.
3. **A JSON shape failure, and the model supports no constrained mode**
   (a stronger mode fails on it, or Kiln's default for it is
   `json_instructions` or `json_mode`), when the model is a lever: a model
   that supports `json_schema`, with the mode that step 4 of the model
   lever gives:
   [model swap inside a class](references/improving_agents/techniques/model-swap-inside-a-class.md).
4. **A format rule that nothing enforces, or a JSON shape failure that
   remains under the strongest mode the model accepts:**
   [state the output contract](references/improving_agents/techniques/state-the-output-contract.md).
   One prompt line that states the contract exactly.
5. Read the residual failures of that candidate. When an edge case remains
   (an escaping case, the empty case), add one line for that case, with the
   same
   [technique](references/improving_agents/techniques/state-the-output-contract.md),
   in the next candidate.

## What not to do yet

- No skill and no tool for a format failure. A mode or one prompt line
  costs less. A model swap only under the condition of step 3.
- Do not change the mode on a task that returns free text. It has no
  effect there.
- Do not copy the text of the eval or of its judge into the prompt. State
  the rule in new words (the leak rules of
  `references/knowledge/train_val_test.md`).
- Do not repeat a rule that the prompt already states. When the model
  ignores a rule that is there, the problem is where the rule is, or the
  length of the prompt.

## Budget

Steps 1, 2, 4 and 5 are cheap: a fork of the run config, a quick check, or one
prompt line. Step 3 is a model swap: a scan of the class and a full experiment.
On a small budget it comes last,
or it waits for a run where this failure is the main goal.

## The output modes, ranked

The lever [output_mode](references/levers/output_mode.md) says what Kiln sends in
each mode. By how reliably the output matches the schema, from the most
reliable to the least:

1. `json_schema`. The provider constrains the output to the schema, where
   it supports this.
2. `json_instruction_and_object`, `function_calling` and
   `function_calling_weak`, about equal. The first gives the schema as text
   and asks the provider for a JSON object. The other two give the schema
   as a tool that the model must call. `function_calling` adds the strict
   flag, and some providers enforce it. Kiln refuses these two on a run
   config that attaches a tool or a skill.
3. `json_mode`. The output is valid JSON, but Kiln does not send the
   schema. The shape comes only from the saved prompt.
4. `json_instructions` and `json_custom_instructions`. Instructions only:
   nothing asks the provider for JSON.

The legacy `default` is `json_schema` on Ollama and Docker Model Runner
(rank 1). On the other providers it is a tool call: rank 2, with the
same refusal.

A higher mode is not always better on a given model. A model can fail
under a mode that Kiln does not recommend for it, and on some models a
constrained mode stops the tool calls. A screen decides.

Confidence: medium. The ranking follows from what each mode sends: a
constraint at the provider holds more than a request, and a request holds
more than text. It is not a measurement, and no case here compares the
modes.
