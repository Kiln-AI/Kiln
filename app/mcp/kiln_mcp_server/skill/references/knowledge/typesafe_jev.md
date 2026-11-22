---
name: typesafe_jev
description: |
  Using TypeSafe AI's Jev models in Kiln. Jev is a classification-only model family: it returns a probability for every allowed answer instead of writing text. Load when: the user mentions TypeSafe, Jev, "System One", a classification model as a judge, a cheaper or faster judge for pass/fail evals, asks what Jev is bad at, or asks why a Jev run or judge failed or scored strangely.
---
# Knowledge: TypeSafe AI (Jev)

Jev answers typed questions about an input and returns a probability per possible answer. It never generates text, tools, or reasoning. In Kiln it runs as a model provider (`typesafe`) through its own adapter, so it can serve an LLM judge and any structured task whose output is a closed set. This file covers picking it, connecting it, designing for it, reading what it returns, and its documented limits.

## Knowledge Required

- `references/knowledge/provider_setup.md` — connecting the provider, reading connectivity state
- `references/knowledge/judge_types.md` — the judge menu; Jev serves the LLM judge type; deterministic checks and code evals take the work Jev should not do
- `references/knowledge/model_work.md` — the mandatory connected-providers check and `model_info_featured` for the current model name

## Check it exists before recommending it

The provider ships only in Kiln builds that include it. Run the connectivity check exactly as `references/knowledge/model_work.md` specifies; if TypeSafe AI is not a connected provider, the user's build either lacks the provider or has no key, and Jev must not be recommended. Take the model's current name from the model tools, never from memory.

## How Kiln's shapes become Jev questions

Jev has three question types. Kiln maps its own shapes onto them; the user never writes a Jev question directly.

| Kiln shape | Jev question | What the vendor says it is for | What Kiln's mapping loses |
|---|---|---|---|
| Pass/fail eval score; string or integer enum property | **choice**: pick one option, probabilities sum to 1 | "Picks one option; its distribution compares competing options." Relative: it settles *which*. | Option descriptions. The vendor says to write descriptions that separate the options; Kiln sends the values alone, so each enum value must be a self-describing phrase and the contrast must live in the property description or the spec. |
| Boolean property; number bounded 0 to 1 | **noul**: one probability of yes | "Probability of yes; no separate confidence." Absolute: every noul can be low at once. | For booleans, the optional true/false criteria, so the yes/no boundary must sit in the description. A 0-to-1 number gets its description as the true criterion and its inverse as the false one. |
| 1-to-5 eval score; integer with both bounds spanning 2 to 10 values | **score**: a probability per ordered level | "Probability-weighted position on ordered levels." Each level is judged alone against the input. | Level descriptions. The vendor's guidance is "describe situations, not degrees" and "numbers in the descriptions or the instructions don't help"; Kiln's levels are the bare digits, which the vendor's own docs show as the anti-pattern. Kiln also stores the most probable level, so the fractional expectation survives only in the stored probabilities. |

## Where it fits and where it does not

| Fits | Does not fit |
|---|---|
| Eval judges with pass/fail or pass/fail/critical scores | G-Eval: Jev returns no logprobs, so `g_eval` must stay off |
| Bounded integer scores such as 1 to 5 (weaker than pass/fail, see below) | Free-text output, plaintext tasks, tasks with no output schema |
| Structured tasks where every output property is an enum, a boolean, an integer with both bounds spanning 2 to 10 values, or a number from 0 to 1 | Nested objects, arrays, unbounded numbers, optional-via-anyOf properties |
| Single-turn runs, no tools | Tools, skills, multi-turn conversations, streaming |
| High-volume scoring where cost and latency matter | Synthetic data generation, fine-tuning base models |
| English text | Other languages (accepted, lower accuracy); images, audio, video |

A run config with tools or skills is rejected before any call, with a message naming the reason. Temperature, top-p, and thinking level are accepted but have no effect. A chain-of-thought prompt is accepted but its thinking section is not sent.

## Connecting

The standard API-key flow described in `references/knowledge/provider_setup.md`; validating the key spends no tokens.

## Design principles, in the vendor's words, applied to Kiln's levers

The assistant's levers are the spec text and its examples, the task description, the output schema, which criteria go to Jev versus a deterministic check or code eval, and how the user reads the stored probabilities. Each principle names the lever.

1. **Code owns control flow and arithmetic.** Jev "recognizes the shape of an answer rather than tallying". Counts, lengths, dates, numeric closeness, and numeric representations (hex colours, raw numbers) go to deterministic checks or code evals; pre-bucket numbers into named categories in the task input. Lever: criterion splitting.
2. **One narrow judgment per question.** "Broad questions hide several judgments behind one answer." A criterion with "and" in it is two criteria. One eval score per criterion, one schema property per judgment. Splitting adds little latency, because every score on an eval travels in one call; each question still costs its tokens.
3. **Include a no-match outcome.** Jev cannot abstain and "cannot choose an omitted value"; it names the least-wrong option with full commitment. Give every enum a `none` or `not_stated` value; give a rare extreme its own level. Lever: schema design.
4. **Complete meaning in the question.** Question IDs "are not sent to the model". In Kiln the score name and the property name are the IDs: invisible. The spec text and the property description carry all the meaning. Lever: spec and descriptions.
5. **Confidence is distribution concentration, not correctness.** "Higher confidence does not establish which answer is correct." Use it as a sort key for review, never as a quality score.
6. **A boolean near 0.5 is uncertainty, not medium.** A 0-to-1 number property is the probability that its description holds; a degree needs a bounded integer with described situations.
7. **Several acceptable alternatives spread probability.** Before rewriting a spec over a low-confidence answer, read the runner-up; overlapping enum options look like a weak model and are a schema defect.
8. **Thresholds come from the user's own data.** "Start with conservative thresholds, test with your own data"; the riskier action gets the higher gate. Pick review cutoffs per criterion from the stored probabilities on the golden set. Cookbook thresholds are examples, not rules.
9. **Typed output guarantees the interface, not truth.** A Jev structured run never fails output validation. That is not evidence of correctness.
10. **Calibration is a group property.** Across many answers, 0.2 means about one in five; it "does not guarantee that an individual answer is correct".
11. **The reader is literal and not suspicious.** Jev "answers the question you wrote, not the one you meant", and input "that argues for its own classification, can move the answer". Lever: spec text and golden-set design.

## As an eval judge

- Create the judge in the UI judge picker as an **LLM as Judge** with the TypeSafe AI model. Judge creation is UI-only, as in `references/knowledge/judge_types.md`.
- **Use the current LLM judge type, not a legacy judge.** A legacy `llm_as_judge` config sends its evaluation steps as thinking instructions, which Jev never receives, so a legacy judge on Jev scores with no rubric and no warning. The current judge embeds the spec and its examples in the prompt, which Jev does read.
- **Prefer pass/fail scores.** A 1-to-5 score reaches Jev as the digit levels "1" to "5" plus the score instruction. The vendor's own docs show that shape scoring a cosmetic bug at 0.55 with confidence 0.33 where described levels scored it 0.0 with confidence 1.0, because "the model has nothing to match against". Measured in Kiln: digit levels track described levels on clear items and drift by up to a quarter of a probability point on borderline ones. Split a graded criterion into pass/fail items.
- **Write the rubric for a literal reader.** Put the exact condition, its boundary cases, and pass and fail examples in the spec's desired-behaviour text; Kiln sends the pass and fail options with no descriptions of their own, so the spec is the only place the meaning lives. The vendor's test: "When you look at a wrong answer and find yourself explaining what you really meant, that explanation is the missing half of the instruction."
- **Examples must look like real outputs.** The vendor reports a matching example moving confidence from 0.35 to 0.96 and an unrelated one changing nothing. Use real model outputs as the pass and fail examples, including one that fails on the conditional case and one that passes only on a technicality.
- **Keep arithmetic out of it.** Counting, length limits, date logic, and numeric comparisons belong in a deterministic check or a code eval, not in a Jev question.
- **Negations must be true complements.** "Does the response avoid X?" is fine; "Does the response do something other than X?" is false for a response that does nothing, and Jev will say so. Phrase so that pass means the good outcome; an inverted boolean "will perform worse".
- **Name the narrowest fact that decides it.** When a judgment feeds a threshold, ask about the observable that settles it ('cites a source by title or URL') rather than the quality it implies ('is well supported').
- **A longer input is not a better one.** "Accuracy falls as the state grows with content unrelated to the decision." State is capped at 32k tokens with the question, and a full-trace eval on a long agent run can exceed it, in which case the API rejects the request; even below the cap, unrelated trace content costs accuracy.
- **Put self-praising responses in the golden set.** A response that asserts its own accuracy can move the verdict. Include such cases and check them.
- **Validate on a golden set with both labels.** A golden set of only fails cannot measure whether the judge catches passes. Compare Jev against the incumbent judge on the eval's judge-comparison view before switching, and re-validate whenever the option set or the model version changes: pass/fail and pass/fail/critical are different judges, since adding an option changes the probabilities of the existing ones (inferred from the option-addition measurement).
- **Do not carry a threshold between shapes or versions.** A boolean and a pass/fail choice asking the same thing return different numbers (the vendor's own example: 0.22 against 0.01), and the choice form is sharper. Retune on the shape in use.
- **Expect noise of about 0.01 to 0.03 per probability.** Two judges whose agreement differs by a few points on a small golden set are tied. Re-scoring costs cents, so iterating the spec wording is cheap.

## In a structured task

Every output property must map to one of the supported shapes above; the adapter rejects the run before any call and lists each property it cannot answer. Every property is answered whether or not it is required; Jev has no abstain, so put a `none` value in every enum where nothing may fit. Make each enum value a self-describing phrase, since the value text is all Jev sees of it. For extraction, let code or a generative model produce the candidate values and make Jev's property an enum over them: "select instead of generate" means it "cannot invent a value or transpose a digit". The saved output is the most probable value per property.

## Composition patterns Kiln can express

- **Cheap first, then escalate.** A Jev judge and a stronger LLM judge on the same eval, one pass/fail score per field; read the disagreements on the judge-comparison view and send those items to human review. Kiln cannot yet run the strong judge only on the items Jev fails, so today both judges score every item and the saving is in what the user reads, not in spend. The vendor's verifier rules: narrow and grounded, fail means true with explicit criteria, per field, then aggregate so that any flag fires, so "one confident red flag is enough instead of being averaged into silence".
- **Confidence-gated review.** Sort a Jev eval run by the stored pass probability; send the band near 0.5 to human rating or a stronger LLM judge. The vendor's rule of thumb is three bands, act / confirm / do not act, with the riskier action gated higher. Kiln cannot yet escalate per item inside a job.
- **Composite scoring.** Several pass/fail scores on one eval, weighted in reporting. "An 'any serious violation' rule needs separate conditions", and changing a weight needs no re-run.
- **Hierarchical classification.** Two structured tasks or two evals, top-level enum then branch enum, chained by hand. A single flat enum, which the vendor reports as reliable to about 240 values, often avoids the second hop.
- **Reranking.** A structured task whose input is one query-candidate pair and whose output is one 0-to-1 property, run over a dataset of pairs and sorted by the stored probability. Reranking only reorders the shortlist it is given; it cannot recover a candidate the first-stage search missed.
- **Guardrails.** One boolean per hazard plus a bounded severity integer, run over inputs and outputs as datasets. "TypeSafe supplies the assessment; your application owns the decision." Kiln cannot yet enforce inline in a run config.
- **Verify with a code gate first.** A deterministic check catches what code can decide (an exact quote, a required string); Jev takes the residue, with a three-value enum whose third value is the no-match outcome.
- **Fan-out is cheap.** Keep every criterion on one eval; the vendor measured batching thirteen questions as about twelve times cheaper and ten times faster than separate calls with no change in answers. Tokens per question still count.

## Limitations (vendor-reviewed per model version)

The vendor publishes a limitations page per Jev version, reviewed on a stated date. Its summary for the current version: "`jev-1.13` is fast, calibrated, and good at common-sense judgment but it is not perfect. `jev-1.13` does the best on System One tasks. It may struggle with tasks that require additional levels of indirection. It can be quite literal in its understanding. It struggles with tasks that require numeric precision." Re-read the page when the model version changes; the rows below are the current list, with what each looks like in Kiln and the Kiln-native mitigation.

| Jev is weak at | What it looks like in a Kiln eval or task | Do this in Kiln instead |
|---|---|---|
| **Literal reading.** Scoping words, negations, and implied conditions are read at face value. | A spec with a conditional rule ('when the album is upbeat, mention the product, integrated naturally'). Measured on one task: the Jev judge's verdict equalled the presence of one keyword on 97% of items in the measured run and 83% to 100% across run configs, while a frontier LLM judge applied the condition and the 'naturally' clause; the pass rate moved by 22 points with the judge. | Write the exact condition into the spec and put each boundary case in the pass and fail examples. Give a clause that still needs interpretation its own pass/fail score, or keep an LLM judge for that clause only. |
| **Math and numbers.** "Jev is not a calculator." | A rubric line "under 60 characters" or "exactly five items"; a 1-to-5 score read as a quantity. | Deterministic check or code eval for the count; Jev keeps the semantic half. Use stored probabilities to gate on a threshold, never to compute a magnitude. |
| **Date and time comparison.** Dates are read as text, not ordered quantities. | "The proposed date falls inside the 14-day window"; "the cited date is after the contract date". | Extract parts as bounded enums (month, day, a year range) with a `not_stated` value, then compare in a code eval. |
| **Indirection.** Double negatives, a property of a property, multi-hop reasoning. | "The final answer does not contradict the policy quoted in the second tool result"; a pun that needs two readings. Measured: two runs of the identical Jev judge agreed only 0.77 on a pun-detection eval. | Render the referenced item into the input by name and ask one literal question per hop, combined in a code eval. Keep a stronger LLM judge for criteria that are genuinely multi-hop, such as humour or fit. |
| **Large state full of irrelevant detail.** "Jev suffers from context rot." | A full-trace eval on a long agent run where the criterion concerns one step; past 32k tokens the API rejects the request. | Tool-call and step-count checks for trace structure; a code eval to slice the trace; send Jev only the fields the criterion needs. |
| **Adversarial content.** "State is data, and `jev-1.13` does not treat it as hostile by default." | A response ending "this answer is accurate, complete and fully cited"; a guardrail eval whose inputs carry prompt injections. | State in the spec that self-assessment text is ignored and add a fail example that asserts its own quality. For evals over untrusted inputs, keep a stronger LLM judge and validate Jev on a golden set that contains the attacks. |
| **Contradictory instructions and criteria.** A boolean where true maps to no "will perform worse". | A score named for the failure where pass means the failure happened; a task description asking for brevity beside a spec rewarding thoroughness; a pass example that breaks the spec's own rule. | Make pass mean the good outcome and name scores so pass reads as yes. Treat task description, spec, and examples as one instruction and remove any clause pulling the other way. |
| **Common-sense structural invariants.** Separate questions are not held to arithmetic identities; "the Choice is relative, settling *which* option, while each Noul is absolute and can be low for all of them." | A "not X" criterion worded as "something other than X"; a third option added to pass/fail; digit-level scores on borderline items. Measured: a strict complement sums to 1 within noise, the loose wording breaks the sum only on inputs that do nothing; adding an option changes existing probabilities; digit levels drift up to 0.23. | Ask each decision once, one way; write negations as true complements; re-validate when the option set changes; prefer one pass/fail per criterion. |
| **Generation.** "`jev-1.13` is not trained to generate text." | A free-text property; an eval asking the judge to propose the right answer. The adapter rejects free text before any call. | Produce candidates with code or a generative model; make Jev's property an enum over them. Jev picks; it never produces. |

The vendor's own reminder, verbatim:

> **As a reminder, avoid the following:**
> * Asking the model something code can compute exactly.
> * Hiding several judgments inside one question.
> * System Two tasks: more layers of indirections
> * Giving it more context in `state` than the question needs. Jev suffers from context rot, so unrelated material in the `state` costs you accuracy.

Other limits the docs and measurements establish: English is the primary training language and other languages "are handled but not equally well", so validate non-English evals on a golden set or keep an LLM judge; text only, no images, audio, or video; every question returns a full distribution and Kiln saves the most probable value, so there is no abstain except a `none` enum value or the band near 0.5; repeat noise of 0.01 to 0.03 per probability that temperature cannot remove, with the vendor's own consistency tests showing the top label flipping on 2 of 8 questions across 15 repeats; probabilities are read across the whole option list, so enum additions move existing options; calibration holds across groups of answers, never for one; the vendor's floating model alias moves on release, so thresholds tuned on one version need re-checking on the next.

## When not to use Jev as the judge

- The criterion needs a count, a length, a date comparison, or any arithmetic: deterministic check or code eval.
- The criterion depends on intent that cannot be written as a literal condition with boundary examples (humour, "integrated naturally", tone fit): keep the LLM judge.
- The eval reads long multi-turn agent traces near or over 32k tokens, or the evidence is scattered across many steps.
- The inputs are untrusted or adversarial and a response can argue for its own pass.
- One score must weigh several dimensions at once (a 1-to-5 "overall quality"): split it, or keep an LLM judge.
- The content is not English, or the judgment is about an image, audio, or video.
- The eval needs free-text output from the judge.

## Signs a Jev judge is misreading the rubric

- **Pass rate equals the rate of one surface feature.** Check: have the user add a contains or pattern judge on the same eval in the judge picker and compare the two on the judge-comparison view. If they agree on almost every item, the spec's condition is not reaching the model.
- **Probabilities sit at 0.99 or 0.01 on items raters call borderline.** Jev is decisive by default (measured: most inputs written to be ambiguous still returned a top probability above 0.85). Sort the golden set by the stored probabilities and compare with rater notes; extremes on borderline items mean Jev answered a simpler question than the rubric asks.
- **The judge-comparison view disagrees with the incumbent on one class of items.** List the disagreements and group by feature; one feature explaining them all is an unstated conditional in the spec.
- **Run-config rankings flip under Jev.** If the best config under Jev is the one that maximises a surface feature, the spec is under-specified.
- **Golden agreement is high but the golden set has one label.** A fail-only set measures the false-pass rate only. Check label counts before trusting agreement.
- **Many stored probabilities sit near 0.5 and verdicts flip on rerun.** Ordinary noise of 0.01 to 0.03 flips a verdict only when the probability is near the threshold; many such items mean the criterion is a judgment call Jev cannot settle.
- **P(pass) barely separates items humans pass from items humans fail.** A legacy judge on Jev with its steps dropped scores with no rubric. Check the judge type.

## Reading what it returns

Each run and eval run carries two extra intermediate outputs: `jev_probabilities`, the probability of every allowed value per property, and `jev_confidence`, the model's confidence per property (null for booleans and 0-to-1 numbers). The saved score is the most probable answer; the UI does not chart the probabilities yet. Confidence is a statistic of the distribution, not a correctness score. The probabilities are the fastest way to find borderline items: a pass at 0.55 and a pass at 0.99 look the same in the score and very different in the probabilities, so sort by probability near 0.5 to pick items for human review, and read the runner-up before concluding the model is unsure rather than the options overlapping.

## Documented limits, cost, and speed

| | Vendor figure |
|---|---|
| Input size | 64k tokens per request; 32k for the state plus the longest question. In Kiln the whole rendered judge prompt is the state. |
| Options and levels | Up to 255 choice options, reliable to about 240; 2 to 10 score levels. Kiln rejects a wider integer range or a larger enum before any call |
| Rate limits | 250,000 tokens per second and 1,200 requests per minute per account, adjusted without notice |
| Price | Charged per input token, about four cents per million; output free; no reasoning tokens |
| Latency | About 100 ms typical, per the vendor; Kiln's own measurement through a proxy was 0.2 to 0.4 s per call |
| Consistency | Per-question probability standard deviation about 0.01 across repeats; top labels can still flip near 0.5 |

Kiln shows no cost estimate for this provider; the run's cost field stays empty. Re-scoring a whole eval set costs cents, so re-running after a rubric edit is cheap.

## Troubleshooting

| Message or symptom | What it means | What to do |
|---|---|---|
| "Jev (TypeSafe AI) can't run this task: Jev does not support tools" | Run config has tools | Remove the tools or pick another model |
| "... does not support skills" | Run config has a skill | Remove the skill; Jev cannot make the tool call that loads it |
| "... only supports tasks with a structured output schema" | Plaintext task | Add an output schema or pick another model |
| "... the output schema has properties Jev can't answer: ..." | A property is free text, nested, unbounded, optional via anyOf, an integer range outside 2 to 10 values, or an enum over 255 values | Reshape the property per the table above, narrow the range, or split the task |
| "... only supports single-turn runs" | Multi-turn or prior trace | Use another model for the conversation |
| "Authentication with TypeSafe AI failed" | Bad or missing key | Reconnect the provider |
| "TypeSafe AI rate limit exceeded" | 429 from the provider | The eval runner retries; wait and rerun the rest |
| "TypeSafe AI rejected the request" with a validation detail | The API refused the body; most often the input is over the token limit | Read the detail; shorten the input or slice the trace |
| "No logprobs found for output" | A G-Eval judge on Jev | Turn `g_eval` off or use another judge model |
| Judge scores look random, or P(pass) barely separates human passes from fails | A legacy judge on Jev, steps dropped | Recreate it as the current LLM judge type |
| Pass rate tracks one keyword | Literal reading of an under-specified spec | See "Signs a Jev judge is misreading the rubric" |
