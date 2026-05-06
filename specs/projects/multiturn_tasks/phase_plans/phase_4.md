---
status: complete
---

# Phase 4: Multiturn run flow + conversation view

## Overview

Frontend-only. Wire the multiturn-task UX end-to-end:

- Branch the `/run` page so a successful multiturn run navigates to the run-detail page (single-turn unchanged).
- Build three new components under `app/web_ui/src/lib/ui/conversation/`:
  - `conversation_view.svelte` — groups a `TaskRun.trace` into turns and renders a `TurnCard` for each.
  - `turn_card.svelte` — renders a "Turn N" header, user markdown, optional collapsible reasoning + tool blocks, then assistant markdown.
  - `composer.svelte` — sticky Send box at the bottom of the run-detail page; reuses `RunInputForm` (plaintext) and `RunConfigComponent`; defaults its config from the previous run; POSTs `/run` with `parent_task_run_id`; auto-focuses textarea.
- Branch the dataset run-detail page (`/dataset/[project_id]/[task_id]/[run_id]/run/+page.svelte`) so a multiturn task renders `<ConversationView>` + `<Composer>` instead of the existing single-turn input/output pair (properties panel and rating UI on the leaf are reused). On Send the page calls `goto(...{ replaceState: true })` to swap the URL to the new leaf and reloads the run.

End state: the user creates a multiturn task, hits Send on `/run`, lands on the run-detail page rendered as a conversation, and can continue the conversation from a sticky composer that persists the previous run config as default.

## Steps

1. **`app/web_ui/src/lib/ui/conversation/turn_card.svelte` — new file.**
   Props:
   ```ts
   export let turn_index: number
   export let user_text: string
   export let assistant_text: string
   export let reasoning_content: string | null = null
   export let tool_messages: TraceMessage[] = []
   ```
   Renders:
   - Outer card: `border border-base-300 rounded-lg bg-base-100`.
   - Header strip: `Turn {turn_index}` (small, muted, `border-b`).
   - User block: `font-medium text-sm` label "User", then `<ChatMarkdown text={user_text} />`.
   - If `tool_messages.length > 0`: a `<details>` with summary "Tool calls ({tool_messages.length})" and a `<pre>` of formatted JSON for each tool call/result.
   - If `reasoning_content`: a `<details>` with summary "Reasoning" and `<ChatMarkdown text={reasoning_content} />`.
   - Assistant block: label "Assistant" + `<ChatMarkdown text={assistant_text} />`.
   - Use `data-testid="turn-card"` on the outer wrapper, `data-testid="turn-card-tool-block"` on the tool details, `data-testid="turn-card-reasoning-block"` on the reasoning details.

2. **`app/web_ui/src/lib/ui/conversation/conversation_view.svelte` — new file.**
   Props:
   ```ts
   export let trace: Trace
   export let task: Task
   ```
   Build turns by iterating the trace:
   - Skip `system` and `developer` messages.
   - Walk forward; on each `user` message, open a new turn. Append intervening `tool` / `function` messages and `assistant` messages with only `tool_calls` (no string content) into the turn's `tool_messages`. The first `assistant` message with non-empty string `content` closes the turn.
   - Pull `reasoning_content` from the closing assistant message (if present).
   - User text is the user's `content` flattened to a string. Assistant text is the assistant's `content` flattened to a string.
   - Render `<TurnCard>` per closed turn, plus an open turn (no assistant_text yet) for any trailing user message — though in v1 we only render closed turns, since we navigate to the leaf only after a successful exchange.
   - Helper `flatten_content(c: string | unknown[] | null | undefined): string` extracts text content; for arrays, joins all `text`-typed parts.
   - Use `data-testid="conversation-view"` on the wrapper.

3. **`app/web_ui/src/lib/ui/conversation/composer.svelte` — new file.**
   Props:
   ```ts
   export let task: Task
   export let project_id: string
   export let previous_run: TaskRun
   export let on_send: (new_run_id: string) => void
   ```
   - Imports `RunInputForm`, `RunConfigComponent`, `client`, `KilnError`, `createKilnError`, `isKilnAgentRunConfig`, `tick`, `onMount`.
   - Local state: `pending_text = ""`, `submitting = false`, `error: KilnError | null`, `model: string`, `selected_run_config_id: string | null`, `prompt_method: string`, `tools: string[]`, `skills: string[]`, `temperature`, `top_p`, `structured_output_mode`, `thinking_level`. These are seeded from `previous_run.output.source.run_config` when the run config is a kiln_agent (otherwise sane defaults).
   - On mount: pull defaults from `previous_run`, then auto-focus the textarea via the form ref or `document.querySelector("textarea#composer-input")`.
   - Render: `RunInputForm` bound to a textarea, then `RunConfigComponent` collapsed inside a `<details>` (summary "Change run config"), then a Send button (primary). The Send button is disabled when `pending_text.trim() === ""` or `submitting`.
   - `handle_send()`:
     - Set `submitting = true`, clear `error`.
     - Build run config properties via the `RunConfigComponent`'s `run_options_as_run_config_properties()`.
     - POST `/api/projects/{project_id}/tasks/{task_id}/run` with `run_config_properties`, `plaintext_input: pending_text`, `parent_task_run_id: previous_run.id`, tags `["multiturn_run"]`.
     - On success: call `on_send(new_run_id)` and clear `pending_text`.
     - On error: keep `pending_text`, set `error`.
     - Finally: `submitting = false`.
   - Sticky styling: `sticky bottom-0 bg-base-100 border-t border-base-300 pt-4`.
   - Use `data-testid="composer"` on the form wrapper, `data-testid="composer-send"` on the Send button, `data-testid="composer-input"` on the textarea (or a wrapper around it), `data-testid="composer-error"` on the inline error block.

4. **`app/web_ui/src/routes/(app)/run/+page.svelte` — branch on send success.** In `run_task()`, after `response = data` and before `posthog.capture`/scroll-to-output, check:
   ```ts
   if ($current_task?.turn_mode === "multiturn" && data?.id) {
     await goto(`/dataset/${project_id}/${task_id}/${data.id}/run`)
     return
   }
   ```
   Place this branch *after* `posthog.capture` (so we still record the run) but *before* the scroll-to-output `tick()`. On the early return we still want `submitting = false` to be reset — keep the existing `finally` block (move the goto into the `try` body before the response render).

5. **`app/web_ui/src/routes/(app)/dataset/[project_id]/[task_id]/[run_id]/run/+page.svelte` — branch render for multiturn.** Currently the body renders:
   ```svelte
   <div class="flex flex-col xl:flex-row gap-8 xl:gap-16 mb-8">
     <div class="grow">…Input…</div>
     <div class="w-72…">…PropertyList…</div>
   </div>
   <Run initial_run={run} task={$current_task} {project_id} />
   ```
   Wrap with a branch on `$current_task.turn_mode`:
   - `single_turn` (default): existing layout untouched.
   - `multiturn`:
     - Render `<ConversationView trace={run.trace ?? []} task={$current_task} />` in a `grow` column.
     - Keep the existing `PropertyList` aside (and `See All` toggle).
     - Render `<Run initial_run={run} task={$current_task} {project_id} />` for the leaf rating + intermediate-output panels (no input/output duplication — `Run` already renders the leaf turn's run details; this is acceptable per `architecture.md` "leaf's metadata is rendered once").
     - Render `<Composer task={$current_task} project_id={project_id} previous_run={run} on_send={handle_send} />` at the bottom.
   - Add `handle_send(new_run_id: string)`:
     ```ts
     async function handle_send(new_run_id: string) {
       run_id = new_run_id
       run = null
       loading = true
       await goto(`/dataset/${project_id}/${task_id}/${new_run_id}/run`, { replaceState: true })
       await load_run()
     }
     ```
   - Use `data-testid="multiturn-layout"` and `data-testid="single-turn-layout"` on the two branch wrappers so the smoke test can distinguish.

## Tests

New tests under `app/web_ui/src/lib/ui/conversation/`:

- **`turn_card.test.ts`**:
  - `renders user_text and assistant_text via markdown and shows the turn index header` — mount with simple text, assert "Turn 3" in DOM, assert user/assistant text visible.
  - `does not render reasoning block when reasoning_content is null` — assert `[data-testid="turn-card-reasoning-block"]` is absent.
  - `renders collapsible reasoning block when reasoning_content is provided` — mount with reasoning_content; assert `<details>` exists; assert open state defaults to closed (no `open` attribute) and toggles on click.
  - `renders collapsible tool block only when tool_messages is non-empty` — mount once with empty array (absent), once with one tool message (present).

- **`conversation_view.test.ts`**:
  - `groups a 2-turn trace into 2 turn cards` — feed a trace [system, user1, assistant1, user2, assistant2]; assert two `[data-testid="turn-card"]` rendered, in order.
  - `groups a 3-turn trace correctly` — feed 3 turns; assert 3 cards.
  - `skips system and developer messages` — system/developer at front shouldn't produce a turn.
  - `folds tool call messages into the requesting turn` — trace [user1, assistant(tool_calls), tool, assistant_final]; assert a single turn card with `assistant_final` text; tool block visible inside.

- **`composer.test.ts`**:
  - Mock `$lib/api_client.client.POST` and `$lib/stores`/`$lib/stores/run_configs_store`/`$lib/stores/prompts_store` so `RunConfigComponent` mounts without network calls.
  - `Send is disabled while pending_text is empty` — render with previous_run; assert button disabled. Type text; assert enabled.
  - `posts parent_task_run_id and calls on_send with new run id on success` — type text, click Send; assert `client.POST` called with body containing `parent_task_run_id: previous_run.id` and `plaintext_input: <text>`; assert `on_send` called with `"new-run-99"`.
  - `disables Send while submitting` — make POST a hanging promise; click Send; assert button disabled and shows submitting state.
  - `preserves text on error and exposes Retry` — POST returns `{ data: null, error: { message: "boom" } }`; click Send; assert text still in textarea, error visible. Click Retry (or just Send again); assert second POST happens.
  - `seeds run config from previous_run.output.source.run_config` — pass a previous_run whose `run_config.model_provider_name === "openai"` and `model_name === "gpt-4o"`; assert the `RunConfigComponent` initial `model` value is `"openai/gpt-4o"` (read by reading the props; or assert the POST body contains those values when send is fired without changes).

- **Page-level smoke test** for the dataset run-detail page is challenging because `+page.svelte` imports a lot of stores. The phase-plan-required smoke is: render with `$current_task.turn_mode === "multiturn"` and a non-null `run` → `[data-testid="multiturn-layout"]` exists; render with `single_turn` → `[data-testid="single-turn-layout"]` exists. This test lives at `app/web_ui/src/routes/(app)/dataset/[project_id]/[task_id]/[run_id]/run/+page.test.ts`. If full mocking proves intractable in vitest, we keep this test minimal: mock all stores and the API client, then assert only the data-testid presence after the run loads.

## Out of scope

- Streaming.
- Tool approval flow.
- Multiturn + structured output.
- Forking UI.
- Eval / finetune integration.
