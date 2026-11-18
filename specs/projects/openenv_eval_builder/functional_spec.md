---
status: complete
---

# Functional Spec: Eval Builder cases grounded in an OpenEnv server

The design and the reasons behind it are in `project_overview.md`. This document states what the
build does, step by step, and what is decided now versus after the prototype.

## Scope

**In scope (v1):**
- Multi-turn Eval Builder runs whose target run config uses tools from an OpenEnv server.
- The planner's `guidance` gains a section built from the server's reset schema, and the Data
  Guide field's text.
- A grounding agent in the app checks each case against a fresh environment, fills in the
  simulated user, and writes `openenv_reset` and the case's judge guidance, or drops the case.
- Each case is driven in its own episode, judged against its judge guidance, and saved with both.
- The eval records the OpenEnv server its cases were grounded in.
- Step 2 (judge authoring) reads OpenEnv tools from the server instead of raising.

**Out of scope (v1):**
- Grounding single-turn evals. A single-turn eval on an OpenEnv run config works as it does today,
  ungrounded, once step 2 stops raising. Single-turn inputs are written locally by
  `generate_inputs_batch`, a different engine from multi-turn's kiln_server case generation, so
  grounding them is its own project.
- Servers behind a login. `OpenEnvServer` has no auth fields.
- Showing what changed in the environment in the trace view.
- Editing a case's reset arguments or judge guidance on Review Cases.
- Any kiln_server change.

## Phase 1 is a prototype

The grounding agent's quality on the user's model is the biggest risk, so it is built and measured
before any UI work.

- A developer command, no UI. It takes an OpenEnv server URL, an eval definition (name and
  specification text) and a case count.
- It builds the new planner `guidance` from the server's reset schema, calls kiln_server's
  existing batch planner, calls kiln_server's existing simulated-user generation, then runs the
  grounding agent on each case. It writes every intermediate result to a folder.
- Compare against the eb3 runs in the integration-tests repo, using the same eval definitions and
  the same server: how many cases ground, how often a setup argument is needed, whether the
  planned scenarios fit the starting states, and whether the references are right on a read-through.
- The prototype's results decided the grounding model, the drop screen and the reference format below.
- It runs against a local Seahaven that has both Kiln-AI/Seahaven#51 (the reset schema on the
  standard `/schema`, which is the only place Kiln reads it now) and #52 (fixture descriptions in
  that schema). The two conflict in `fill_fixture_ids` and its tests, so a local branch merges them.
  The world under test is served on that checkout with OpenEnv 0.13, which #51 requires, through a
  local dependency override that is not committed to the world's repo. Testing the full flow in
  the Kiln UI later needs the same setup until both PRs ship.

## The flow, for a multi-turn build on an OpenEnv run config

Screens are unchanged: the plan proposal, Generation Settings, the progress takeover, the
"Errors During Dataset Creation" screen, Review Cases, save.

1. **Run config.** The user picks a run config whose tools come from an OpenEnv server. The
   server is found from the config's tool ids (`kiln_tool::openenv::<server id>::…`), and the eval
   records it ("The eval's OpenEnv server", below).
2. **Judge authoring tools.** `_collect_task_capabilities` reads the server's tools with
   `OpenEnvSessionManager.list_tools`, which needs no episode. A server it can't reach fails this
   step with the server's URL and the error.
3. **Plan.** The app builds `guidance` (below) and calls kiln_server's batch planner, unchanged.
4. **Simulated users.** kiln_server writes one simulated user per approved plan item, unchanged.
5. **Grounding.** The grounding agent runs once per case (below). The progress line reads
   "Checking cases against the OpenEnv server: 7 of 20", with a running count of dropped cases.
6. **Drive.** Each grounded case runs in a fresh episode reset with its `openenv_reset`, the way
   `eval_runner._run_v2_job_in_openenv` runs saved evals. The task run keeps `openenv_episode`,
   with `final_state`.
7. **Judge.** The judge prompt adds the case's judge guidance and `final_state` (below).
8. **Review and save.** Review Cases shows each grounded case's reset arguments and judge
   guidance, read-only and collapsed by default. Save writes `openenv_reset` and
   `reference["judge_guidance"]` to each `EvalInput`, and `openenv_server_id` to the `Eval`.

A build whose run config has no OpenEnv tools behaves exactly as it does today.

## Planner guidance

The app appends two sections to the `guidance` text, after the multi-turn guidance and before the
Refine Plan steer. `compose_plan_guidance` still appends the steer last. The proposed prompt text is
on the plan page's "Prompt changes" tab.

### Reset arguments section

- Read from the server's reset schema through the session manager.
- Lists every argument with its `description`, and its values when it has a fixed set (`enum`).
  An object argument is walked into, so a nested keyword is listed by its path (for example
  `startup.acting_user`), resolving local `$ref`s.
- Leaves out `seed` and `episode_id`, which OpenEnv itself defines.
- Uses no argument names: no special case for `fixture` or any other name.
- Opens with the framing for the planner: each conversation runs in a fresh environment; Kiln picks
  the reset arguments after planning; write scenarios that fit at least one starting state; spread
  the batch across them; take kinds of things, never specific names or IDs; change a scenario no
  starting state could support.
- Left out entirely when the server publishes no reset schema.

### Data Guide section

- The project's multi-turn synthetic user guide (below), with framing: take the people and kinds of
  requests from it, follow any frequencies it gives, and let the specification decide what each
  scenario stresses.
- Left out when the guide is empty.

### Dropped cases section

Added only on a Retry after drops, before the Refine Plan steer, which stays last. It lists each
dropped scenario with its reason, and tells the planner these could not be checked against the
environment, so it should not plan them again in the same form.

### Rule-12 line

For OpenEnv runs, `multiturn_plan_guidance` no longer says the planner can't see what the system
contains. It says the reset arguments describe the starting states, and that scenarios still name
kinds, never records.

## Multi-turn synthetic user guide

- One free-text guide per project, for multi-turn builds: who uses the project's agents and what
  each kind of user asks. Written once and reused by every multi-turn build in the project, instead
  of a field the user fills in for each eval.
- The planner's Data Guide section and the grounding agent read it. Left out when it is empty.
- Used for every multi-turn build, OpenEnv or not, since who uses the agent matters either way.
- **UI to be scoped** (Sam): where the guide is edited, and how a build shows that it is using it.
  This replaces the per-build field decided earlier, which made the user paste it again for each
  new eval.

## Grounding agent

### Input

- The eval's specification text, so the case keeps testing what the specification tests.
- The target task's prompt: what the agent under test is told.
- The project's multi-turn synthetic user guide, when there is one, for who the user plausibly is.
- The approved plan item's prompt.
- kiln_server's simulated user for it: `seed_prompt`, `<persona>`, `<goal>`, optional
  `<behavior_guidance>`.
- The server's full reset schema, with descriptions.
- The server's `readme_content` from `GET /metadata`, as extra context. Nothing depends on it.
- The target run config's tool list, so it knows what the agent under test can call.

### Tools

- `start_episode(reset_kwargs)`: a fresh environment. Each call throws the previous one away.
- The server's own tools, inside the current environment.

### Behavior

1. Picks reset arguments whose starting state fits the scenario; a starting state the scenario names
   is only a hint. If an argument chooses who the session acts as, sets it to someone whose role
   matches the persona, using the synthetic user guide for who the user plausibly is without overriding the
   persona. It finds that argument from the schema's descriptions, not by name. A server without
   one skips this. If the schema has a `seed` argument, it always passes one (a value the schema
   allows) and keeps it in the final reset, so the case replays the same way.
2. Finds what the scenario needs with whatever tools show the environment's state. Prefers what the
   starting state already has, then other starting states whose descriptions suggest they have it,
   keeping resets in reserve for setup and the final reset. An environment with nothing to read
   goes straight to step 4.
3. If nothing fits and a setup argument's description (or the readme) says what it accepts, writes
   the smallest setup that adds it, consistent with the data around it, then resets and checks. If
   nothing says how, it does not guess: it drops the case.
4. Rehearses what a well-behaved agent would do for this user and observes the result, reading it
   back where a tool can, otherwise from tool results and the episode's `state()`.
5. Fills in the simulated user: changes only the specifics (the person the session acts as, and
   real IDs, names and values where the scenario has the user know them). Keeps wording, tone,
   difficulty and `<behavior_guidance>`.
6. Writes the reference from what it observed, about results rather than steps.

### Output

Either `grounded`, with `openenv_reset.reset_kwargs`, the edited simulated user and `reference`;
or `dropped`, with a one-sentence reason. The case keeps testing what the specification tests: the
agent never switches it to a different feature or kind of object to make it fit. Drop when nothing
fits after checking the likely starting states and setup, the
scenario needs something the server can't represent, or the rehearsal fails for a reason the agent
under test couldn't avoid.

### Limits and concurrency

- Per case: 40 tool calls, 10 resets, 15 minutes. Hitting a limit drops the case with that reason.
- Cases ground in parallel, with the same pool size `run_cases_batch` uses to drive cases.
- A server refusing a session (its concurrency cap) is retried like other transient errors, not a
  drop.
- Every episode it starts is ended, including on error and cancel.

### Model

The grounding agent runs on the **Judge Model** chosen in Generation Settings. There is no separate
grounding control: grounding writes each case's answer key and the judge grades against it, so
both want the same strong model, and the user never picks a "grounding agent".

- Generation Settings comes after the plan is approved and before generation starts, so the model
  is known before any case is grounded. The batch planner runs on kiln_server and uses no user
  model.
- For a build on an OpenEnv run config, the judge lane also requires tool support. A recommended
  judge model without it moves to "Not Recommended" with the lane's reason, as the dropdown does
  for other filters. The lane's tooltip says it also checks each case against the environment.
- The judge's recommended list and the data-gen list are the same 41 model and provider pairs
  today, so reusing the data-gen lane would not give a shorter list.
- The measured run after phase 3 checks that a cheaper recommended judge model grounds well. If
  it does not, grounding gets its own lane.

## Reference

Stored as one markdown string, `EvalInput.reference["judge_guidance"]`. Kiln judges already read
reference data by key (`reference_keys`, then `{{ reference_data.<key> }}` in the prompt), so any
judge, including one a user writes after the builder, uses it by naming that one key. The UI tells
the user so where they write a judge.

The grounding agent still returns a typed reference, so that every fact carries its evidence and a
malformed answer is caught (`invalid_output`). Kiln renders it to markdown when the case is saved;
the typed form is not stored.

```
starting_point: str                  # what is true before the conversation
facts: list
  text: str
  evidence:
    tool: str                        # the call the grounding agent made to learn it
    args: dict
    result_excerpt: str
expected_outcome: list[str]          # what must be true at the end, or what the agent must say
allowed: list[str]                   # acceptable alternatives, e.g. asking first
must_not_happen: list[str]           # changes or claims that fail the case
```

The markdown has one heading per field: Starting point, Facts (each fact with its tool call and
result excerpt), Expected outcome, Allowed, Must not happen. An empty list keeps its heading with
"None."

Evidence records how the fact was learned, so a person can re-run the call. It is not the path the
agent under test must take. A later machine-checkable form, if the judge results call for one, is
a second key beside `judge_guidance`, not a replacement.

## The eval's OpenEnv server

Run configs are not tied to an eval: a user runs one eval against many run configs, and the run
config picked in the builder may never be used again. The grounded cases only make sense on the
server they were grounded in, so the eval records it: `Eval.openenv_server_id`, `None` for an eval
with no grounded cases.

- **v1.** Set once, from the run config picked in step 1 of the builder. Every saved
  `EvalInput.openenv_reset.openenv_server_id` equals it.
- **Follow-up.** Show the server on the eval, warn when the eval is run with a run config whose
  tools come from another server or from none, and decide whether a user can change it.

## Judge

- One template for every server, built in `build_judge_prompt_template` and saved as the eval's
  judge.
- Sets `reference_keys=["judge_guidance"]` and adds `{{ reference_data.judge_guidance }}`, and
  `final_state` when the episode has one.
- Grades the end result and what the agent told the user, not which tools it called. A path fails
  the case only when `must_not_happen` names it.
- An input with no judge guidance (an ungrounded case) is judged as today.

## Simulated user in grounded cases

For a case with a reference, the app's driver prompt drops its "accept a not-found reply" rule, so
the simulated user pushes back when the agent says something it was given doesn't exist. Other
cases keep the rule. kiln_server's own rule 5 only shapes the draft, which the grounding agent then
fills in.

## Errors and edge cases

| Situation | Behavior |
|---|---|
| Server unreachable during grounding or driving | The step fails on the existing "Error Creating Eval Dataset" screen, with the server URL and error, and its existing Retry. No case is dropped for it. |
| Server publishes no reset schema | The reset arguments section is left out; the grounding agent resets with no arguments. |
| No starting state fits a case | The agent tries a setup argument if one is described, otherwise drops the case. |
| Some cases drop | "Errors During Dataset Creation" lists each dropped case's scenario with its one-sentence reason (`drop_detail`), under three actions: **Continue With N** saves the grounded cases; **Retry** runs the batch again, with the dropped scenarios and their reasons added to the planner guidance ("Dropped cases section", below); **Cancel** ends the build. v1 does not plan replacements for only the dropped cases. |
| Every case drops | The same screen without Continue. |
| Grounding agent hits a limit | The case drops with the limit as its reason. |
| User cancels | Every open episode is ended. |
| Run config has no OpenEnv tools | Today's flow, unchanged. |

## Docs

Kiln's OpenEnv docs say that a server's reset-schema descriptions guide eval generation, so they
should be written for models: what each starting state holds, who a session can act as, and how
any setup argument works.

## Follow-ups after v1

- The eval's OpenEnv server in the UI (above).
- Planning replacements for only the dropped cases.
