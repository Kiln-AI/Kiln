---
status: complete
---

# Functional Spec: Train/val/test splits across V1 and V2 eval datasets

## 1. What this is

An eval carries three named dataset **splits** — `train`, `val`, `test` — plus a separate
`golden` set. Today only the TaskRun data source has all three, and only the test split can be
backed by `EvalInput`. This project makes **every split independently backable by either data
source**, addressable through one API surface, so no caller branches on where an eval's items
live.

This unblocks the EvalInput-based projects downstream. It ships before them; they align to the
model it lands, not the other way round.

### The core model (decided)

- There are three splits: **test**, **train**, **val**.
- Each split is backed by exactly **one** data source — `TaskRun` or `EvalInput`. Never both,
  never neither-when-required.
- An eval **may mix** backings across its splits. An eval with a TaskRun test and train set may
  gain an `EvalInput`-backed val set. This is a requirement, not an accident: it's how someone
  adds a val set to an existing eval using the new tooling.
- **Golden is not a split.** It stays exactly as it is — `eval_configs_filter_id`, TaskRun-only,
  and expected to be unpopulated in V2 as the product backs away from human-alignment scoring.
  It is not touched by this project.

### The design goal

The splits × sources matrix is 3 × 2. Handled naively it produces a source branch at every call
site, and every new reader adds another. The whole point of this project is that it doesn't: the
model and its accessors resolve "which items are in split X" and "which item did this EvalRun
score" once, and callers stay source-agnostic. Chasing `if eval_set_filter_id is not None: ...
elif eval_input_filter_id is not None: ...` around the codebase is the failure mode this exists
to prevent.

---

## 2. Terms

| Term | Meaning |
|---|---|
| **Split** | A named subset of an eval's items: `test`, `train`, or `val`. |
| **Backing / source** | Which store a split's items come from: `TaskRun` (V1) or `EvalInput` (V2). |
| **Filter id** | The stored selector for a split. `DatasetFilterId` for TaskRun backing, `EvalInputFilterId` for EvalInput backing. Not interchangeable — see §7. |
| **Golden set** | `eval_configs_filter_id`. Human-rated TaskRuns used to score *judges*, not models. Out of scope. |
| **Judge axis (V1/V2)** | `EvalConfig.config_type`. Independent of the data-source axis; untouched here. |

"Eval set" in existing field names and copy means the **test** split. The name is legacy.

---

## 3. Split semantics

### 3.1 Which splits exist

- **test** is required. Every eval has one, with one backing.
- **train** and **val** are optional. An eval may have neither, either, or both.
- Splits are disjoint by convention (tagging discipline), not enforced. Nothing in this project
  validates or requires disjointness.

### 3.2 Unconfigured splits stay unconfigured

An eval with no train or val split **has no train or val split**. Nothing mints one on load.

Today a lazy migration stamps `tag::train_{name_slug}` (and, on the superseded branch,
`tag::val_{name_slug}`) onto any eval loaded without one. That is removed. It cannot survive the
model in §3.1: minting a split requires choosing a backing, and choosing TaskRun by default
silently locks the legacy source onto a split nobody configured — including on evals whose other
splits are EvalInput-backed. A split's backing is a real decision and belongs to whoever creates
the data, who knows which store the items live in.

It also manufactured a split that never had items. Both real creation paths — spec eval creation
and the copilot — set the train split explicitly at creation. The migration only ever applied to
legacy evals predating the field, and nothing ever tagged those runs `train_{name_slug}`, so the
minted filter resolved to the empty set. It converted "this eval has no train set" into "this
eval has an empty train set", which reads as configured and isn't.

Consequences, all intended:

- Eval progress reports **0** for an absent train or val split (§6.1). Absent and empty both read
  as zero; the run API is where the distinction is stated precisely.
- `split=train` or `split=val` against an eval with no such split returns 422 (§9). This now fires
  for most pre-existing evals rather than almost none — correctly, since those splits have no
  items.
- Prompt optimization reports no usable train set for legacy evals that previously relied on the
  minted filter (§6.3). Those runs would have optimized against an empty set; they now say so
  instead of proceeding.

Evals whose minted value was already persisted by an earlier save keep it. It is an explicitly
set, TaskRun-backed train split from that point on, and nothing rewrites it.

### 3.3 Where splits come from instead

Splits are set explicitly by whoever creates the eval's data, with the backing they intend:

- **Spec eval creation** mints the tags and filter ids for its splits at creation time. It gains a
  val split alongside the existing test and train ones, TaskRun-backed like its siblings.
- **The copilot** sets its splits explicitly today and continues to.
- **The incoming EvalInput tooling** sets EvalInput-backed splits when it creates the items. That
  work belongs to that project, not this one — this project only has to make the field it writes
  exist and mean something.

An eval created without a train or val split simply has none until something sets one.

### 3.4 Naming

A split's stored name identifies **the split it defines**, never the source that backs it.
`eval_input_filter_id` violates this twice over: it names the source, and it silently means
"test".

If the storage shape keeps a flat field per (split, source), the new name is
**`test_eval_input_filter_id`** — split first, source second, matching `train_…` / `val_…`
siblings. If the shape instead nests splits, the field disappears rather than being renamed, and
the same principle is expressed structurally: the split is the key, the source is a property of
its value. Either way `eval_input_filter_id` does not survive.

A temporary load-time shim carries the old value across to whichever shape lands, marked with a
`TODO` to be removed before this ships. Only internal projects contain the key, so the shim is a
throwaway and needs no long-term compatibility story.

The V1 field `eval_set_filter_id` has the same naming defect — it means "test" and says
"eval set" — but it is in shipped public projects, so it cannot be renamed on the same terms.
Whether it survives, is renamed with a permanent read-path, or is absorbed into a new shape is
part of the storage-shape decision in §10, where file compatibility constrains the answer.

---

## 4. Running an eval against a split

### 4.1 Entry point

`POST /api/jobs/evals/run` takes an optional `split` parameter: `"train" | "val" | "test" | null`.

| `split` | Behavior |
|---|---|
| `null` (omitted) | Runs the eval's test split. **Byte-identical to today's behavior** — see §8. |
| `"test"` | Same item set as omitting the param. |
| `"train"` / `"val"` | Runs that split, if the eval has one. |

The split's backing determines which store is iterated. A caller does not know or care: the same
request shape runs a TaskRun-backed val set and an EvalInput-backed one.

**This endpoint ships separately, and is not on `claude/eval-splits-evals-v2`.**
`POST /api/jobs/evals/run` is served by the eval job worker in
`app/desktop/studio_server/jobs/`, which does not exist on `scosman/evals_v2` — it belongs to the
still-draft PR #1517. So on this branch the route is absent, and with it the `split` parameter:
nothing in the generated `api_schema.d.ts` mentions it. The work that adds `split` to it is
built, reviewed and complete (phase 5, commit `369a32ef8`), and re-lands on a tree that has the
worker. See `implementation_plan.md`'s phase 5 entry.

The note covers §4.3 as well, since a *job's* progress total is the worker's to compute. What is
on this branch is everything below the request layer: the runner takes a resolved split rather than
a filter id, §4.2's guarantee is structural — so re-adding the endpoint cannot reintroduce a
dropped override — and `len(ResolvedSplit)` is the correct universe for either backing, which is
what §4.3's progress total is measured against. §4.4 is unaffected: the SSE endpoints are here and
still do not take a `split`.

### 4.2 The split must actually reach the runner

The requested split replaces the eval's default item selection **for both backings**. A split
request that is silently ignored — succeeding with a 200 while running the full test set — is
the single worst outcome in this project and must be impossible by construction, not by
convention. The runner must not have a path where an override is accepted and then dropped.

### 4.3 Progress and resumption

A running job's progress total is computed against **the split's** item universe, in the split's
own store. A partial run of one split, resumed, must not short-circuit against a different
split's or a different store's item count.

Already-scored items are reused at item granularity, so running overlapping splits does not
re-score shared items. This holds per-source: an item's identity for caching is (source, item
id), never the id alone.

### 4.4 Unsupported combinations

`split` is not offered on the SSE run endpoints (`run_comparison`, `run_calibration`). The UI
runs the test split only; train and val are deliberately not surfaced there — they exist for
auto-research and programmatic callers, which use the jobs API.

---

## 5. Reading results by split

`GET .../eval_config/{eval_config_id}/run_config/{run_config_id}/results` takes a **required**
`split` query parameter.

| `split` | Behavior |
|---|---|
| `"test"` / `"train"` / `"val"` | Only results whose scored item is a member of that split. |
| omitted | 422. There is no default, and no way to request a mixed set. |

Filtering happens at query time against stored `EvalRun`s. There is no `EvalRun` schema change,
so it works retroactively on results recorded before this project.

**Caller update.** The endpoint has exactly one caller in the repo — the "Eval Results" page
(`.../[eval_config_id]/[run_config_id]/run_result/+page.svelte`) — and it passes `test`, which is
exactly what it renders today.

Making the parameter required rather than defaulted means the regenerated OpenAPI client types it
as required too, so a caller that fails to pass it is a **build failure, not a runtime 422**. Any
caller added between now and merge is caught the same way. That is a large part of why required
is the right call here: the breaking change is enforced at compile time in the one place it
matters, instead of being discovered by a user looking at a table with the wrong rows in it.

### 5.1 Why `split` is required here but optional on the run API

Making it required is a deliberate breaking change, and the reason is that the current default is
only *accidentally* correct.

Today every stored `EvalRun` is a test-set run, because the test set is the only thing that has
ever been runnable. So "all results" and "test results" are the same list, and the page that
renders them is right by coincidence. The moment this project makes val runnable, that same
request returns a mixed table with no indication that it did — and the endpoint is agent-exposed,
so an agent asking for "the results" silently gets a mixture too. Keeping the parameter optional
would preserve the *syntax* of today's behavior while silently changing its *meaning*, which is
worse than breaking it visibly.

A mixed set is not requestable at all. There is no caller that wants results from more than one
split at once: every consumer is either rendering a split or scoring a split. Offering an "all"
value would just re-introduce the mixed response as an option, and the first thing any honest
consumer would do with it is filter it back down.

The **run** API keeps its optional `split` defaulting to test (§4.1), and that asymmetry is
intended rather than an oversight. Omitting `split` when running picks a set of work to do, and
there is one obvious default — the test split, which is what running an eval has always meant.
Reading has three equally meaningful answers and no obvious default, so silence is ambiguous and
is rejected rather than guessed at.

That gives the general rule this project holds to:

> **Every response about eval results is scoped to exactly one split — whether it returns
> per-item records or an aggregate. No endpoint returns a mixed-split set.**

The existing summary endpoints already satisfy this: they aggregate only over items in the eval's
test split and ignore runs outside it. Nothing in this project may introduce a response computed
over an unscoped mixture. In an aggregate it would be invisible — a val item quietly averaged
into a test score — and in a per-item list it would be indistinguishable from a correct one, since
results carry no split marking (§5.2).

### 5.2 No per-result split label

Results are not labelled with the split they came from, and don't need to be: the caller named
the split in the request, and the whole response is that split.

A label would also be the wrong thing to add. Splits are disjoint by convention only (§3.1) —
nothing enforces it, and an item may legitimately match two splits' filters — so a single split
field per result would be ambiguous or wrong exactly when it mattered. Scoping the request is
unambiguous by construction; labelling the response isn't.

### 5.3 Membership is source-aware

Membership is tag-based, and **one item can be in several splits**. An `EvalInput` tagged both
`val_x` and `test_x` is a member of both splits, and both `?split=val` and `?split=test` return
its results. That is expected — splits are disjoint by convention only (§3.1) — and nothing here
restricts it.

The source-awareness point is a different one: it's about **which store a filter is evaluated
over**, not about how many tags an item carries.

A filter id is a predicate, not a location. `tag::val_x` is a valid selector in *either* store —
run it over `task.runs()` and it yields TaskRun ids, run it over `task.eval_inputs()` and it
yields EvalInput ids. The string is identical in both cases. What decides which store it reads is
the split's backing, which is recorded on the split, not encoded in the filter id.

So resolving a split yields ids **from one store**, and an `EvalRun` records exactly one of
`dataset_id` (TaskRun) or `eval_input_id` (EvalInput). Testing membership means comparing ids
that must come from the same store to mean anything. A TaskRun-backed run is not a member of an
EvalInput-backed split — not because of anything about its tags, but because it is not the kind of
thing that split contains.

**The ids alone cannot be trusted to enforce that.** Kiln ids are `str(uuid.uuid4().int)[:12]` —
twelve decimal digits from one generator shared by every model type. That is a ~10¹² space, not a
full UUID, and TaskRuns and EvalInputs draw from it identically. Cross-store collisions are
unlikely, not impossible, and a collision here doesn't fail loudly: it silently admits one item's
result into another item's split. Any cache key, lookup, or membership test must therefore carry
the source alongside the id or filter id, rather than relying on ids being globally distinct.

---

## 6. Endpoint behavior by data source

### 6.1 Things that work for both backings

Any surface whose question is *"how many items are in this split"* or *"which item did this
EvalRun score"* works for both backings, because both resolve through the shared accessor. That
covers:

- `GET .../evals/{eval_id}/progress` — test-split size, train size, val size
- `GET .../eval_config/{eval_config_id}/score_summary`
- `GET .../eval_results_summary`
- `GET .../run_config/{run_config_id}/results`
- run-config comparison / the compare page

Each field returns its true value, which for an EvalInput-backed eval means:

| Field | Value |
|---|---|
| Test / train / val split sizes | The real count, resolved in that split's own store |
| Score summaries and aggregates | Computed over that split's real items |
| Golden counts | **0** — golden is unset, and zero is the correct answer |

**Zero where zero is true, real numbers everywhere else.** Golden counts are zero because there is
no golden set, which is the expected V2 state (§1) and not an error. Split sizes are never
reported as zero when the split has items — that would be worse than an error, since it tells a
user their test set is empty when it isn't.

These endpoints currently 400 for EvalInput-backed evals. That guard is not a policy decision
about golden — it fires because the code can only count `TaskRun`s and has nothing to say when
the test split lives elsewhere. Once the accessor can count either store, there is nothing left
to refuse, and keeping the guard would take *more* code than deleting it. So the guards go.

The 4xx from the earlier round still stands — it just belongs to §6.2, on the one operation that
genuinely cannot be performed, rather than to these endpoints, which can now answer honestly.

### 6.2 Things that genuinely cannot work, and must fail loudly

**Judge evaluation over EvalInput items** (`eval_config_eval` mode, `run_calibration`). This
scores a judge by re-using a dataset item's *stored output* without re-running the task, and
compares it against a *human rating*. `EvalInput` has neither an output nor rating storage. It
is not a gap to be filled later by better plumbing; the data isn't there.

Required behavior: refuse up front, with a message that names the eval, the operation, and the
reason. Specifically it must **not** proceed to manufacture a persisted `EvalRun` per item marked
skipped — that turns an unsupported operation into durable junk records that every downstream
reader then has to reason about. The refusal happens before any item is processed or written.

**Golden set over EvalInput.** `eval_configs_filter_id` remains TaskRun-typed and is never
populated from EvalInput items. Not an error condition — just a thing that doesn't exist. No new
validator restricts golden based on an eval's split backings.

### 6.3 Prompt optimization

Prompt optimization is the only consumer of the train split outside evals. It packages the
project and hands it to the closed-source remote Kiln service, which resolves the train filter
against the project zip's `runs/` directory. That zip does not contain `eval_inputs/`, and the
resolver is in another repo.

So: **prompt optimization supports TaskRun-backed train splits only.**

- Its "does this eval have a usable train set" check reports true only when the eval has a train
  split **and** that split is TaskRun-backed.
- Starting a job against an eval whose train split is EvalInput-backed fails with a 4xx naming
  the reason, rather than optimizing against an empty set.

Teaching the remote service EvalInput is a separate project in a separate repo. It is not
blocked by this one — this one just has to be honest about the boundary.

---

## 7. Filter id types

`DatasetFilterId` admits `all`, `high_rating`, `thinking_model`, `thinking_model_high_rated`,
`tag::<x>`, and `multi_filter::<...>`. `EvalInputFilterId` admits only `all` and `tag::<x>`,
because the others read TaskRun ratings and thinking data that `EvalInput` does not have.

A TaskRun-only filter form must never be storable on an EvalInput-backed split. Enforcement
should come from the model's shape wherever possible rather than a hand-maintained validator,
since a validator is another thing that can be forgotten when a fourth split or a third source
appears.

Conversely, a filter id string alone never identifies its source. `tag::val_x` is valid for both.
See §5.

---

## 8. Compatibility requirements

1. **The run path does not move.** Omitting `split` on the run API produces exactly today's
   behavior for TaskRun-backed evals: same items run, same progress totals. The parameter is
   opt-in there and existing callers are unaffected.

   The **results** endpoint is the deliberate exception: `split` is required (§5.1), which breaks
   callers that omitted it. This is intentional — that default is only accidentally correct today
   and becomes silently wrong as soon as a non-test split is run. A caller that omitted it was
   getting test results; passing `test` reproduces exactly what they had. In-repo the change is
   one page and a regenerated schema; the endpoint has not shipped in a release carrying runnable
   non-test splits, so there is no correct external caller to break.
2. **Stored results stay readable.** No `EvalRun` schema change. Results recorded before this
   project filter correctly by split afterwards.
3. **Existing project files keep working.** TaskRun-backed evals in shipped public projects load,
   run, and save correctly. A load/save round trip neither drops a field nor **invents** one —
   which is why the train/val lazy migration goes (§3.2).

   The one intended user-visible change: a legacy eval that never had a train split explicitly set
   now reports as having none, where it previously reported an auto-minted filter that matched no
   items. Nothing that ran before stops running; something that silently did nothing now says it
   has nothing to do.
4. **The internal-only rename is a throwaway.** The `eval_input_filter_id` shim exists to carry
   internal projects across and is removed before ship, tracked by a `TODO`.
5. Whether new-format files remain readable by **older Kiln builds** is an open constraint that
   feeds the storage decision — see §10.

---

## 9. Error behavior

Errors name the split, the eval, and the actual reason. In particular:

- A request for a split the eval does not have must not report a missing field that has never
  existed under that name. Diagnostics are written in terms the caller used (`train`, `val`,
  `test`), not internal field names.
- A bad split on a run request fails at request time, not as a background job that starts and
  then dies. This one is about the jobs API and ships with it (§4.1) — the requirement stands, and
  the pre-resolution that satisfies it is written and reviewed, just not in this tree.
- Unsupported operations (§6.2) fail before any work is done or any record is written.

| Condition | Result |
|---|---|
| `split` names a split the eval doesn't have | 422, naming the split and the eval |
| `split` value isn't one of train/val/test | 422 from request validation |
| `split` omitted on the results endpoint | 422 from request validation — no default (§5.1) |
| Eval or task not found | 404 |
| Judge evaluation requested over an EvalInput-backed set | 4xx, naming operation and reason; nothing written |
| Prompt optimization against an EvalInput-backed train split | 4xx, naming the reason |

---

## 10. Deferred to architecture

These are design decisions, not functional ones, and each deserves a real proposal rather than a
snap call:

1. **Storage shape on `Eval`.** How three splits × two backings are represented. The candidates
   range from flat per-(split, source) fields to a discriminated splits structure. The choice
   should be driven by which representation makes §7's type safety and §5's source-awareness
   structural rather than validator-enforced.
2. **File compatibility**, which is an *input* to (1), not a separate decision. `eval_set_filter_id`
   and `train_set_filter_id` exist in shipped public projects; whether the new shape reads legacy
   fields only, dual-writes during a deprecation window, or keeps them canonical materially
   changes what shapes are viable — including whether older Kiln builds can still open a migrated
   project, and whether they'd fail loudly or quietly misread it.
3. **The accessor surface.** What "resolve a split to its items" and "identify an EvalRun's item"
   look like as a single well-typed seam, such that adding a source or a split later touches one
   place. This is the anti-if-branch requirement from §1 made concrete.
4. **How the judge-evaluation refusal is implemented** (§6.2) — where the check lives so it can't
   be reached with items already partially processed.
5. **Removing the train/val lazy migration** (§3.2) — where the removal lands relative to the
   storage shape, and confirming no reader treats an absent split as an error rather than a zero.

## 11. Deliverable: an alignment project overview for eb-v2

This project ships first and the eb-v2 line aligns to it. That alignment is real work and it
needs somewhere to live, so **the final phase of this project produces a `project_overview.md`
for it** — a new project folder under `specs/projects/`, proposed name `eb_v2_splits_alignment`.

The deliverable is the overview only: the *what*, in the same role this project's own
`project_overview.md` plays. It is not a functional spec, not an architecture, and not a plan.
Whoever picks that project up runs it through the normal speccing process from there.

**It is deliberately not designed during this speccing.** The implementation agent for the final
phase writes it, and writes it last, because it can only be accurate once the model has actually
landed. The conflict surface between the shipped model and eb-v2's current code is not knowable
from here — the two lines diverged 256 commits ago, eb-v2 is unreviewed and still moving, and the
storage shape isn't chosen yet. Writing it now would mean guessing at all three.

What that phase's agent has to do is read the merged tree and eb-v2's current state and record
what alignment actually requires, in enough detail that the follow-on project can be spec'd
without re-deriving it. Things that will plainly be in the picture — eb-v2's hand-rolled
per-call-site source branching, which the accessor supersedes; its eval-creation path, which
writes splits with mixed backings and predates the renamed field; and the removed lazy migration
— are starting points for that reading, not a scope.

That project is where alignment gets designed. This project's job is to hand it an honest,
current description of the problem rather than a stale one.

## 12. Explicitly out of scope

- **Golden sets and judge/human alignment.** Unchanged, TaskRun-only, expected unpopulated in V2.
- **Data-creation paths.** Populating `EvalInput`s and tagging items into splits at creation time
  belongs to the incoming copilot project. Nothing here builds it, and nothing here is designed
  around a guess at what it will do.
- **EvalInput support in the remote prompt-optimization service** (§6.3) — different repo.
- **UI work** beyond two required changes: adding the val count to eval progress, and the "Eval
  Results" page passing `split=test` for the endpoint that now requires it (§5). Train and val
  stay unsurfaced as run targets by design — no split picker, no new views.
