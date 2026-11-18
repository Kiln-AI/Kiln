---
status: complete
---

# Eval Builder cases grounded in an OpenEnv server

Plan page (diagram of this design over the current code): https://claude.ai/artifact/99YYFkgHghSTN2tcqmSRsh

## Goal

Let the Eval Builder make multi-turn eval cases for a run config whose tools come from an OpenEnv server. Each case should start from a real state on that server and refer to what is really in it. The judge should grade against facts read from the server, not against what a model guessed.

Kiln speaks the OpenEnv protocol. Nothing here may assume one framework's routes, state format or reset arguments. Seahaven is one OpenEnv server among many.

## Rulings already in force

From the design review of 2026-11-09:

- The Eval Builder keeps its five screens. No new step, no headless mode.
- kiln_server does not change. The batch planner still plans shapes, never records (planner rule 12), and anything we want it to know rides in its `guidance` text.
- One new agent, the grounding agent, runs in the Kiln app on the user's keys. It runs once per case inside "Creating Simulated Users", after kiln_server writes the simulated user.
- One batch plan across all starting states, not one plan per state. No code replay.
- The batch planner stays kiln_server's existing one-shot call; the app only adds to its `guidance`. The grounding agent is the only new agent, and it runs in the app (Sam, 2026-11-17).

## How it works

1. The user picks a run config that uses OpenEnv tools. Screen 2 and judge authoring read that config's tools from the server (today `tool_from_id` raises on `kiln_tool::openenv::` ids, which reads as an HTTP 500 from the code).
2. The app builds the planner's `guidance`: the eval guidance it sends today, plus a section built from the server's reset schema and the Data Guide field's text (both below).
3. kiln_server's batch planner returns one prompt per case, unchanged.
4. kiln_server writes a simulated user per case, unchanged: a `seed_prompt` and a `synthetic_user_info` with `<persona>`, `<goal>` and optional `<behavior_guidance>`. The role comes from the plan prompt, which the planner wrote with the reset arguments and the Data Guide field in view. Its rule 5 ("No invented world state") keeps specific records out, so this is a draft.
5. The grounding agent takes each case, picks reset arguments (including who the session acts as, when the server has such an argument), starts a fresh environment, finds what the case needs in it, rehearses the change and observes the result. It fills in the simulated user kiln_server wrote with the real names and details it found, keeping its wording and behavior. It returns an `openenv_reset`, a `reference` and the edited case, or drops it.
6. The builder drives each case inside its own episode, the same way `eval_runner._run_v2_job_in_openenv` does for saved evals, and stores `openenv_episode` (with `final_state`) on the task run.
7. The judge reads the rubric, the reference, the transcript, and `final_state` when the server fills it.
8. Save writes `openenv_reset` and `reference` onto each `EvalInput`.

## What the planner gets

All of this goes through the existing `POST /v1/copilot/batch_plan` fields. Nothing new on kiln_server.

| `BatchPlanApiInput` field | Content | Source |
|---|---|---|
| `guidance` | Eval guidance, as today | Builder |
| `guidance` | Refine Plan steer, as today | Refine Plan dialog |
| `guidance` | New: reset arguments section | The server's reset schema and its descriptions |
| `guidance` | New: Data Guide text (who uses the agent, what they ask) | New field in the Refine Plan dialog |
| `data_guide` | Unchanged. Multi-turn never sends it today (`builder/data_guide_flow.ts:35`) | Task Data Guide |
| `count` | Unchanged | Builder |

### Reset arguments section

Built by the app for each plan from the server's reset schema. There is no separate brief field in v1: the server owner's descriptions are the brief.

- The app walks the reset schema and lists every argument with its `description`, and its values when it has a fixed set (`enum`). Arguments OpenEnv itself defines (`seed`, `episode_id`) are left out. It does not look for an argument named `fixture`; every OpenEnv server names its own.
- Per-value descriptions go in the argument's own `description` text. Kiln's reset form (`openenv_reset_schema.ts`) refuses `oneOf` and `const`, so a server can't describe each value separately.
- Kiln's OpenEnv docs tell server owners that these descriptions guide eval generation, so they should say what each starting state holds, who a session can act as, and how any setup argument works.
- Those descriptions also show under each field in the environment preset dialog. Long ones need a UI fix there, tracked separately.

The section opens with framing for the planner. It explains that each conversation runs in a fresh environment started from reset arguments, and that Kiln picks those arguments and finds what each scenario needs after planning. It then says how to use what follows:
- Write scenarios that fit at least one starting state.
- Spread the batch across starting states.
- Take kinds of things and situations from the descriptions, never specific names or IDs (rule 12 still applies).
- Change a scenario that no starting state could support.

The Data Guide section has its own framing. Take the people and the kinds of requests from it, follow any frequencies it gives, and let the specification still decide what each scenario stresses. The full proposed text is on the plan page's "Prompt changes" tab.

`multiturn_plan_guidance` (`builder/batch_plan_guidance.ts:87`) currently tells the planner that neither it nor the user can see what the system contains. For OpenEnv runs that line changes: the reset arguments say which starting states the server offers and what data each starts with, and rule 12 still applies.

### Data Guide field

Roles and the kinds of questions each one asks belong to the task, not the server. One server can back several tasks. The proper home is the task's Data Guide, but multi-turn Data Guide support is a larger feature. As an intermediate step:

- Add a free-text "Data Guide" field to the Refine Plan dialog. Its hint asks who uses this agent and what each kind of user asks. It stands in for the task's Data Guide, which multi-turn builds do not send.
- Unlike the existing steer box (`plan_steer`), which clears once a plan arrives, this field is kept with the builder draft and applies to every plan.
- Show it before the first multi-turn plan. Today the first plan runs without the dialog, so a field that only appears on re-plan never reaches the first plan.
- When multi-turn Data Guide support lands, this text can seed the guide.

## No new data on `OpenEnvServer`

v1 adds no brief field. A server whose owner wrote thin descriptions still works: the planner gets less context and the grounding agent does more exploring, so more cases may be dropped. For servers the Kiln user can't change, a follow-up adds notes the user writes in Kiln. Environment presets already have a `description`, which is a place to start.

## Grounding agent

Runs in the app, per case, through `OpenEnvSessionManager`.

- **Reads:** the plan prompt and kiln_server's draft simulated user, the full reset schema with its descriptions, and the server's `readme_content` from `GET /metadata` as extra context. Nothing depends on the readme, since it may hold only setup steps. It goes only here, where it can't add noise to the planner's prompt.
- **Does:** picks reset arguments, `start_episode`, looks at the environment with whatever tools show its state and finds what the case needs (data, objects, a condition), rehearses the change and observes the result. An environment may have nothing to read, only tools that act; then the agent goes straight to the rehearsal and takes the outcome from the tool results and `final_state`. Tries the server's own data first, then other starting states. If none fits and a setup argument's description (or the readme) says what it accepts (Seahaven's `setup_sql`), it writes data that fits. If nothing explains how, it doesn't guess at the format; it drops the case. Setup data runs only in that episode's environment and is replayed from `openenv_reset` on every later run. Data it adds must be consistent with the data already there: anything it refers to exists, and anything the server requires is filled in.
- **Who the session acts as:** if the reset schema has an argument that picks the acting user (Seahaven's `startup` keyword), the agent sets it to a person in that starting state who matches the persona's role. It finds the argument from the schema's descriptions, not by name; Kiln has no notion of which argument means "user". A server without one skips this.
- **Fills in the simulated user:** kiln_server already wrote all three fields from the plan prompt. The agent keeps their wording, tone and `<behavior_guidance>`, and changes only the specifics: it puts the real person's name when the session acts as someone, and real specifics (IDs, names, values) where the scenario calls for them, into `seed_prompt`, `<persona>` and `<goal>`, so the user and `openenv_reset` agree. Both are saved on the same `EvalInput`.
- **Returns:** `openenv_reset`, `reference` and the edited case, or drops the case.
- Limits carried over from eb3: 40 tool calls, 10 resets, 15 minutes per case.
- **Biggest risk:** quality on the user's model. Prototype this agent first, against a real server, before building the rest.

## Reference shape

Stored in the existing `EvalInput.reference: dict | None`.

```
reference:
  starting_point: str
  facts: list
    text: str
    evidence:
      tool: str
      args: dict
      result_excerpt: str
  expected_outcome: list[str]
  allowed: list[str]
  must_not_happen: list[str]
```

Text plus tool evidence, so it assumes no server's state format. eb3 used rows from Seahaven's change log, which only Seahaven has. Every OpenEnv server has `list_tools` and `call_tool`.

Evidence is the call the grounding agent made to learn the fact. It is not the path the agent under test must take. It is kept so a person can re-run the call to check a case, and so later check calls can re-run it.

## Judge

One template for every server, in `eval_builder_utils.build_judge_prompt_template`. The same template is saved as the eval's judge.

- Includes: the rubric from kiln_server's judge writer (unchanged), the reference's fact text and result excerpts, expected outcome, allowed, must not happen, the transcript with tool results, and `final_state` when the server fills it.
- Leaves out the evidence's `tool` and `args`, so the judge does not mark down an agent that reached the same fact another way.
- Rule: grade the end result and what the agent told the user, not which tools it called. A path is penalized only when `must_not_happen` names it.
- OpenEnv only promises `episode_id` and `step_count` in state. A server that returns nothing more is judged on the transcript and its tool results, as judges work today. `final_state` is opaque: Kiln never computes a diff itself. The server decides what `state()` reports, and `OpenEnvEpisode.final_state` already allows "a diff against its starting state". Seahaven's default format (`seahaven.state/1`) is its whole change log, so on Seahaven the judge sees exactly what changed. A server with thin state is covered later by check calls.
- `run_judge_for_trace` and `build_claims_for_trace` gain `openenv_episode`.

## Code changes, by area

- `copilot_utils._collect_task_capabilities`: read OpenEnv tools from the server instead of `tool_from_id`.
- `batch_plan_guidance.ts`: reset arguments section, Data Guide section, and the OpenEnv version of the rule-12 line.
- Builder `+page.svelte` / `builder_draft.ts`: the new dialog field, kept in the draft, shown before the first multi-turn plan; send the run config id; carry `openenv_reset` and `reference` through to save.
- `multiturn_sdg_api.GenerateCasesApiInput`: `target_run_config_id`; run the grounding agent after kiln_server writes the users, and return the edited cases so "Review Cases" shows the grounded version.
- `eval_builder_api.run_cases_batch`: a shared helper that starts, sets, drives and ends one episode per case.
- `eval_builder_utils`: judge template and claims as above.
- `copilot_utils.build_multi_turn_eval_inputs`: write `openenv_reset` and `reference`.
- Kiln docs: OpenEnv page says reset-schema descriptions guide eval generation.

## World-side follow-up (Seahaven)

Not needed for Kiln's v1 to work: Kiln reads only standard reset-schema descriptions, and a server with thin ones gets less context. These make Seahaven worlds describe themselves better.

- Each fixture's `fixture.yaml` description is listed in the `fixture` argument's description: Kiln-AI/Seahaven#52, open.
- Not started: the world's tables and a short example in the `setup_sql` description, which is the same generic text for every world today.
- A world's own startup keywords can carry a description already, through `Annotated[..., Field(description=...)]` on the hook's parameter.

## Later, not v1

- Kiln-side notes for servers the user can't change, possibly starting from environment preset descriptions.
- Check calls: re-run reference evidence calls before `end_episode` to see what changed, on any server.
- A suggested starting state on each plan item, so the grounding agent tries those first. Starts as free text in the item; a real field would be a kiln_server change.
- Multi-turn support for the task's real Data Guide, replacing this field. Its text can seed that guide.
- Keeping the Data Guide text between evals (a save button on the task, or prefill from the last build). In v1 the user pastes it again for each new eval.

## Open questions

- The Data Guide field is a new control in the builder. The review ruled no new controls; needs a sign-off.
- Whether grounded cases keep "accept not found". kiln_server's generator rule 5 and the app's own driver prompt (`libs/core/kiln_ai/synthetic_user/prompt.py`, "Conversation style") both tell the user to accept a not-found reply. In a grounded case the record exists, so the user stops pushing; the judge still sees the facts and marks the miss. The app's rule could be relaxed for grounded cases with no kiln_server change.
- OpenEnv servers behind a login. `OpenEnvServer` has no auth fields; local servers work as they are.
- Whether the trace view shows what changed in the environment.
- How many cases the grounding agent drops when a server's descriptions are thin, and how often it needs a setup argument. Measure in the prototype.
