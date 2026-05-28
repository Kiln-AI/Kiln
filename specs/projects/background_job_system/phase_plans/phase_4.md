---
status: draft
---

# Phase 4: Frontend — jobs store, REST client, jobs panel, sidebar badge

## Overview

The final phase. Phases 1–3 built the in-memory `JobRegistry`, the `/api/jobs`
REST + SSE surface, and the first real worker (`EvalJobWorker`). This phase is the
Svelte UI that consumes that surface:

- A store backed by the `GET /api/jobs/events` SSE stream that holds a live,
  keyed `Map<id, JobRecord>`, handling the three named events (`snapshot`,
  `job`, `deleted`) per functional_spec §6.
- A thin typed REST client over the generated OpenAPI `client` for the
  create/list/get/result/errors/pause/resume/cancel/delete endpoints.
- A jobs panel at `/jobs` listing jobs with per-job lifecycle actions (only the
  ones valid for the current status + `supports_pause`), plus drill-in for the
  per-run error log and the result summary.
- A small sidebar badge showing the count of active (`pending` / `running` /
  `paused`) jobs, driven by the same store.
- A nav entry into both the icon rail (`sidebar_rail.svelte`) and the wide
  drawer sidebar (`(app)/+layout.svelte`).

### Key design decisions (resolved from the integration map)

- **Store location.** The repo's strong convention is `src/lib/stores/` (every
  other store + its `*.test.ts` lives there). The spec *suggests* `lib/jobs/`.
  We follow the repo: `jobs_store.ts` and `jobs_api.ts` live in
  `src/lib/stores/`. (The architecture doc's `lib/jobs/` path is explicitly
  "out of strict scope … the natural shape", so matching the repo wins.)
- **SSE named events.** The jobs stream uses `event: snapshot|job|deleted`
  (confirmed in `app/desktop/studio_server/jobs/api.py::_format_sse`). So we use
  `addEventListener('snapshot'|'job'|'deleted', …)`, not the single `onmessage`
  the extractor store uses.
- **Pure observer.** The store opens one `EventSource`, reconnects on error, and
  closes it only when the last subscriber unsubscribes (ref-counted). No job
  action is ever tied to connection lifecycle. A fresh `snapshot` re-syncs the
  map on reconnect (no `Last-Event-ID`).
- **Project filter.** The store opens the stream with
  `?project_id=$ui_state.current_project_id` when one is set; it re-opens the
  stream when the active project changes (the badge / panel are project-scoped,
  matching `?project_id=` list semantics). NoopJobs (no project) only show when
  no project filter is active — acceptable; the panel is project-scoped.
- **Reconnect URL is the schema path constant** but `EventSource` needs a raw
  URL, so we build it from `base_url` (mirroring `extractor_progress_store`),
  not the openapi-fetch `client` (which can't do SSE).

## Steps

1. **`src/lib/stores/jobs_api.ts`** — thin REST client. Re-export the generated
   record type for convenience and wrap each endpoint:

   ```ts
   import { client } from "$lib/api_client"
   import type { components } from "$lib/api_schema"

   export type JobRecord = components["schemas"]["JobRecord"]
   export type BackgroundJobStatus = components["schemas"]["BackgroundJobStatus"]
   export type JobError = components["schemas"]["JobError"]

   export async function list_jobs(query?: {...}): Promise<JobRecord[]>
   export async function get_job(id: string): Promise<JobRecord>
   export async function create_job(type, params, metadata?): Promise<{job_id, status}>
   export async function get_job_result(id): Promise<Record<string, unknown>>
   export async function get_job_errors(id, run_id?): Promise<Array<{error_message?: string} & Record<string, unknown>>>
   export async function pause_job(id): Promise<void>
   export async function resume_job(id): Promise<void>
   export async function cancel_job(id): Promise<void>
   export async function delete_job(id): Promise<void>
   ```

   Each unwraps `{ data, error }` from openapi-fetch and throws `error` when set
   (so callers can wrap with `createKilnError`). Lifecycle calls (`pause` etc.)
   return `void` (the backend returns `202`/`204` with no useful body).

2. **`src/lib/stores/jobs_store.ts`** — the SSE-backed store.

   - Internal `writable<Map<string, JobRecord>>`.
   - `connect()`: builds `${base_url}/api/jobs/events` with optional
     `?project_id=`, opens an `EventSource`, registers listeners:
     - `snapshot`: `JSON.parse(data).jobs` → replace the whole map.
     - `job`: `JSON.parse(data)` (a full `JobRecord`) → upsert by `id`.
     - `deleted`: `JSON.parse(data).id` → delete by `id`.
     - `onerror`: close + schedule a reconnect (small backoff); the next
       `snapshot` re-syncs.
   - Ref-counted lifecycle: `subscribe` increments a counter and `connect()`s on
     first subscriber; the returned unsubscribe decrements and `disconnect()`s
     (closes the `EventSource`, cancels any pending reconnect) when it hits zero.
     Closing never touches a job — pure observer.
   - Re-open on project change: subscribe to `ui_state`; when
     `current_project_id` changes while connected, tear down and reconnect with
     the new filter. (Implemented with an exposed `set_project(id)` the module
     wires to `ui_state`, kept testable by allowing an injected project id.)
   - Derived exports:
     - `jobs`: a `Readable<JobRecord[]>` sorted by `created_at desc` (matches the
       REST default sort) for the panel.
     - `active_jobs_count`: a `Readable<number>` counting
       `pending|running|paused` for the badge.
   - Export an `ACTIVE_STATUSES` set and a helper `is_active(status)` so the
     badge logic is unit-testable without the DOM.
   - To make `EventSource` injectable for tests, read the constructor from
     `globalThis.EventSource` at connect time (tests install a fake on
     `globalThis`).

3. **`src/lib/stores/job_status.ts`** (small helpers, colocated) — pure
   functions used by both the panel and tests:
   - `job_status_display(status)`: human label.
   - `job_status_badge_class(status)`: DaisyUI badge color class
     (`badge-info` running, `badge-success` succeeded, `badge-error` failed,
     `badge-warning` paused, `badge-ghost` pending, neutral cancelled).
   - `available_actions(job)`: returns which of
     `pause|resume|cancel|delete` are valid given `status` + `supports_pause`,
     per state machine (§3) + delete policy (open item #7: terminal only):
     - `running`: cancel; pause iff `supports_pause`.
     - `paused`: resume, cancel.
     - `pending`: cancel.
     - terminal (`succeeded|failed|cancelled`): delete.
   - `progress_label(progress)`: `"{success} / {total}"` (+ error count when > 0),
     and `progress_percent(progress)` for the bar.

4. **`src/lib/components/SidebarJobsBadge.svelte`** — count bubble. Renders the
   `active_jobs_count`; shows a small primary pill with the number when > 0,
   nothing when 0. Designed to overlay the rail icon (absolute, top-right) and to
   sit inline in the wide drawer. Accept a `count` prop (default: subscribe to
   the store) so it's render-testable in isolation; expose a `variant`
   (`rail` | `inline`) for placement styling.

5. **`src/routes/(app)/jobs/+page.svelte`** — the panel. Uses `AppPage`
   (`../../app_page.svelte`) with title "Jobs" and a short subtitle. Subscribes
   to `jobs`. States:
   - Loading: spinner until the first `snapshot` arrives (track a
     `connected/received-snapshot` flag on the store).
   - Empty: educational empty state (icon + heading + one-liner explaining that
     background jobs like evals run here and keep running even if you navigate
     away). No destructive CTA.
   - List: a table (`bg-base-200` header, matching the app's table style) with
     columns: Type, Status (colored badge), Progress (`success/total`, error
     count, thin progress bar), Message, Created, and an Actions cell.
     - Actions render only `available_actions(job)`; each calls the matching
       `jobs_api` fn, wrapped in try/catch → toast/inline error. Optimistic UI
       is unnecessary — the SSE event will reflect the real transition.
     - "Errors" button (always available when `progress.error > 0` or status is
       `failed`) opens a `Dialog` that lazy-loads `get_job_errors(id)` and lists
       `error_message` rows; "Result" button (when terminal + has result) opens a
       `Dialog` showing the result summary JSON in a `<pre>`.
   - Use `formatDate` from `$lib/utils/formatters` for timestamps.

6. **`src/lib/ui/section.ts`** — add `Jobs` to the `Section` enum.

7. **`src/routes/(app)/sidebar_rail.svelte`** — add a `SidebarRailItem`
   `href="/jobs"` with a briefcase/stack icon and an overlaid `SidebarJobsBadge`
   (rail variant). Place it after Evals / before the optimize group.

8. **`src/routes/(app)/+layout.svelte`** —
   - Add the `/jobs` → `Section.Jobs` branch to the section reactive block.
   - Add a wide-drawer `<li>` nav entry mirroring the Evals entry, with the
     inline badge.
   - Import `SidebarJobsBadge`.

## Tests

`src/lib/stores/jobs_store.test.ts` (jsdom, fake `EventSource` installed on
`globalThis`):

- **snapshot replace**: dispatch a `snapshot` with two jobs → `jobs` has both;
  dispatch a second `snapshot` with one different job → map fully replaced.
- **job upsert (insert)**: `job` event for a new id adds it.
- **job upsert (status transition + progress update)**: `job` event for an
  existing id with a new `status`/`progress` replaces the stored record (counts
  reflect the latest snapshot, not accumulated).
- **deleted removal**: `deleted` event removes the id; deleting an unknown id is
  a no-op.
- **reconnect re-sync**: trigger `onerror` → the fake records that `close()` was
  called and a new `EventSource` is constructed after the backoff; a fresh
  `snapshot` repopulates the map (stale entries from before are gone).
- **active count derivation**: a mix of statuses → `active_jobs_count` counts
  only `pending|running|paused`.
- **pure-observer teardown**: last unsubscribe closes the `EventSource`; a job
  action is never invoked by the store (assert no fetch/callback fired on close).
- **project filter**: connecting with a project id builds the URL with
  `?project_id=`; changing the project closes the old source and opens a new one
  with the new filter.

`src/lib/stores/job_status.test.ts` (pure, no DOM):

- `available_actions` returns the correct sets for each status (running w/ &
  w/o `supports_pause`, paused, pending, each terminal).
- `job_status_badge_class` / `job_status_display` map each status.
- `progress_label` / `progress_percent` for total=null, zero, partial, full.

`src/lib/stores/jobs_api.test.ts` (mock `$lib/api_client`'s `client`):

- each wrapper calls the expected client method + path with the right
  params, and throws when the client returns `error`.

`src/lib/components/SidebarJobsBadge.test.ts` (jsdom, render):

- renders the count when > 0; renders nothing when 0.
