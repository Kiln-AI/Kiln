---
status: complete
---

# Artifact Provenance — Project Overview

Add **provenance metadata** to Kiln's compiled/tunable artifacts: a shared Pydantic submodel recording *why an artifact exists* (`notes`), *what it was derived from* (`derived_from_ids`), and *whose judgment created it* (`origin`). Wire every existing Clone function to stamp lineage automatically. This is the artifact-side half of agent memory ("Part 1"); the general memory system is a separate project ("Part 2", see [agent_memory.md](../../../planning/agent_memory.md)).

**Target repo:** `Kiln-AI/kiln` (datamodel `libs/core/kiln_ai/datamodel/`, APIs `libs/server` + `app/desktop/studio_server`, web UI `app/web_ui`), off `main`. Exception: `CodeTool` gets the field inside the [Code Tools project](../code_tools/project_overview.md) (its spec is revised to include it) — coordinate, don't duplicate.

Reference research (O3 planning repo): [datamodel](../../../research/kiln_tech/datamodel.md) (base classes, ID semantics, additive-model conventions, validator-based back-compat), [agent memory APIs](../../../research/agent_memory_apis/summary.md) (adjacent prior art), [DSPy/GEPA deep dive](../../../research/competitive_research/dspy_gepa/report.md) (candidate lineage). Decision log: O3 [discussion queue](../../../planning/discussion_queue.md) Q15.

## Why (one paragraph)

Kiln artifacts are immutable — improvement means deriving a new artifact — but nothing records the derivation: which artifact it forked, why, what evidence justified it, and whether a human or an agent made the call. That knowledge lives in agent context and dies at compaction, so future sessions re-explore dead ends and re-test rejected ideas. The cost of losing failure knowledge is measured: across 24,008 RE-Bench agent runs, failed runs account for **90.2% of dollar cost**, and agents without access to prior failure records must independently rediscover every dead end (["The Last Human-Written Paper"](https://arxiv.org/abs/2604.24658), 2026). O3's doctrine already demands provenance win-or-lose on every experiment (Q5) and provenance on every compiled artifact so a model upgrade can trigger re-test-and-prune ([translation layer research](../../../research/open_questions/translation_layer.md) §5); today the only mechanism is a breadcrumb squatting in `TaskRunConfig.description`. This project gives provenance a real, uniform home — and the auto-research agent consumes it from day 1 (walk the fork DAG, read why each variant exists, treat human-origin artifacts as constraints and agent-origin ones as re-testable prior work).

## Decisions (locked, scosman 2026-07-10)

1. **Shape: one shared nested submodel**, not per-model fields and not a flat mixin. New type `KilnArtifactProvenance` (suggest `datamodel/provenance.py`, exported from `datamodel/__init__.py`); each host model gains a single optional field `provenance: KilnArtifactProvenance | None = None`. `None` = legacy/unknown/created-without-provenance. Rationale: one-line addition per host, directly reusable in API request/response models, evolves without touching hosts, no MRO interaction with the base-class machinery. Precedent: `TaskRun.output.source: DataSource`.
2. **Three fields** (full sketch below): `notes` (free text ≤ 2,000 chars), `derived_from_ids` (ordered multi-parent list), `origin` (`"human"` / `"agent"`).
3. **`derived_from_ids` semantics — git parent conventions:** ordered `list[ID_TYPE]`; **first element = primary parent** (the artifact this one replaces / is a new version of); further elements = additional sources merged in; empty list = not derived from an existing artifact. Multi-parent is required, not speculative: GEPA's merge step emits two-parent candidates, and ARA's exploration graph has an `also_depends_on` convergence field.
4. **Lineage is same-type-sibling only.** IDs are Kiln scope-local IDs (reuse the existing `ID_TYPE` and its validator from `basemodel.py`); resolution = scan your own relationship folder, same as every existing Kiln cross-ref. No universal/global ID scheme exists in Kiln and this project must not invent one — cross-type or cross-scope inspiration goes in `notes` as prose. **Do not build a global index or lineage table**; the DAG is per relationship folder, which matches how agents read it (list siblings, walk locally).
5. **`origin` is a `str`, not an enum** — validated strictly on create (must be `"human"` or `"agent"`), leniently when `loading_from_file` (any string accepted), so future values never brick old clients. Semantics: `"human"` = a person authored it directly **or** an agent created it fulfilling a direct human request ("clone this skill", "write me a prompt that..."); `"agent"` = an agent created it on its own judgment during exploration/optimization. Documented upgrade path if finer grain is ever needed: ARA's four-tag taxonomy (`user` / `ai-suggested` / `ai-executed` / `user-revised`). Note: in an immutable datamodel, "user revised the agent's work" is *not* a tag — it's a new artifact with `origin="human"` derived from the agent's; the DAG carries what ARA needs a tag for. "Agent work approved by a human" is likewise the trust-gate mechanism's job, not `origin`'s.
6. **Model-level validation is format-only.** No existence checks, no cross-sibling lookups in validators (established Kiln rule — they break file loads). Existence and self-reference checks happen at the API layer on create.
7. **Immutability is an API contract** (the CodeTool pattern): `provenance` appears in create request models and is **structurally absent from all PATCH request models**. Written once at creation, never edited; post-creation learnings about an artifact belong in Part 2 memory (with a link), or in the next derived artifact's notes.
8. **Clone stamps lineage, always.** Every Clone function/endpoint in the app sets `derived_from_ids=[source.id]` automatically — human clones included; the user never types an ID. `origin` is stamped from the calling surface: UI clone = `"human"`, agent-invoked clone = `"agent"`. `notes` optional on clone (UI *may* offer a small "why are you cloning this?" text box; empty is fine — the ID is the value).
9. **Evidence stays in `notes` as prose for v1** (cite eval/run_config/trace IDs inline, e.g. "addresses failures seen in traces 1234, 2345; validated by eval run 5678"). Structured `evidence_refs` (typed claim→evidence bindings, making re-test-and-prune mechanically walkable) is the **named v2 follow-on** — designed as an upgrade, deliberately not built now.
10. **Model coverage in two phases** (see Phases). `Eval` is deliberately excluded: the eval is the *goal* and immutable; `EvalConfig` is the tunable *how* and included. `ExternalToolServer` is excluded: the tunable artifact is the tool *list*, which lives on the run config.
11. **`TaskRunConfig.description` breadcrumb retires.** Once this ships, the optimize_loop skill's provenance breadcrumb (win-or-lose verdict trail) moves from `description` into `provenance.notes`, restoring `description` to its real job ("what this config is"). The skill-library update is owned by the O3 repo, coordinated when this feature lands — not part of this kiln project.

## Datamodel sketch (authoritative for field names/descriptions)

```python
class KilnArtifactProvenance(BaseModel):
    """Why this artifact exists and what it was derived from.
    Written once at creation; immutable thereafter (enforced at the API
    layer). Compile-time metadata for future agent sessions and humans —
    never shown to runtime models (not part of any tool/prompt surface)."""

    notes: str | None = Field(
        default=None,
        max_length=2000,
        description="Why this artifact exists: the problem or hypothesis it "
        "addresses, what changed relative to the derived_from_ids parents, "
        "what validation/evidence supports it (cite eval/run_config/trace "
        "IDs inline and state the evidence level), and known limitations. "
        "First line = one-sentence summary. Record observations with "
        "conditions ('batch API 429'd at 50rps on 07-04'), never universal "
        "rules ('batch API doesn't work').",
    )
    derived_from_ids: list[ID_TYPE] = Field(
        default_factory=list,
        description="IDs of same-type sibling artifacts this one was derived "
        "from. Ordered: first = primary parent (the artifact this replaces "
        "or is a new version of); any further entries = additional sources "
        "merged in. Empty = not derived from an existing artifact. IDs "
        "resolve among siblings in the same parent scope only.",
    )
    origin: str | None = Field(
        default=None,
        description="Whose judgment created this artifact. 'human': a person "
        "authored it directly OR an agent created it fulfilling a direct "
        "human request. 'agent': an agent created it autonomously — its own "
        "judgment during exploration or optimization. None: unknown/legacy. "
        "Values may grow over time; consumers must tolerate unknown values.",
    )
```

**Validators (on the submodel):**

- `notes`: strip whitespace; coerce empty/whitespace-only to `None`; enforce the 2,000-char cap post-strip — **create-time only** (on load, over-length notes are accepted). (Caps are write discipline: Letta caps records at 2,000 chars, LangSmith commit descriptions at 1,000.)
- `derived_from_ids`: reject empty/whitespace-only entries and duplicate ids — **create-time only**. There is no `ID_TYPE` format validator in Kiln (`ID_TYPE` is unconstrained `Optional[str]`), so entries are not run through one. On load, the list is accepted as-is (any string or `None`).
- `origin`: strict membership in `{"human", "agent"}` when *not* in the `loading_from_file` validation context; on load, any string **or** `None` is accepted (forward/back-compat — mirrors the existing strict-mode/load-context pattern).

**API-layer rules (per hosting model's endpoints):**

- Create endpoints accept optional `provenance` (the submodel reused as the request component). On create, validate: no entry equals the new artifact's own ID; every entry exists among same-type siblings (archived included — lineage may point at archived losers). 400 otherwise.
- PATCH request models omit `provenance` entirely (functional edits structurally impossible; error copy mirrors CodeTool: "provenance is immutable — it describes creation").
- Read/list endpoints return it. Agent access follows each model's existing policies; nothing about provenance is secret.

**Back-compat:** purely additive optional field — old files load untouched, no `v` bump, no migration. Accepted known risk (same as `is_archived` had): an old client that load-mutate-saves a file written by a newer client silently drops the field.

## Phases

**Phase 1 — core + Tier 1 (the models the compile loop touches today):**

1. `KilnArtifactProvenance` submodel + validators + unit tests.
2. Add `provenance` to all four Tier-1 hosts: **`Skill`**, **`Prompt`**, **`TaskRunConfig`**, **`CodeTool`** — each gets the field + create-endpoint plumbing + clone wiring.
3. **Clone-path inventory (do this first in implementation):** enumerate every Clone function/endpoint in the app across all models; wire each to stamp `derived_from_ids` + `origin`. While inventorying, **assert the cross-scope case does not exist** (no clone path copies an artifact into a different parent scope — believed true; if one is found, stop and flag rather than guessing: the intended fallback is source recorded in `notes`, `derived_from_ids` left empty).
4. API plumbing per Tier-1 model: create accepts provenance (+ existence/self-ref checks), PATCH excludes, reads return.
5. **No provenance display UI** — provenance is agent/disk-facing metadata only (display deferred/out-of-scope). Clone/create forms stamp `provenance` (`origin`, plus `derived_from_ids` on a clone) silently into the create request; nothing is shown on any detail view or Clone dialog.

**Phase 2 — Tier 2 (the tunable surface referenced by run configs):**

6. Add `provenance` + clone wiring + API plumbing to: **`EvalConfig`**, **`Finetune`**, **`RagConfig`**, and the five RAG component configs (**`ExtractorConfig`**, **`ChunkerConfig`**, **`EmbeddingConfig`**, **`VectorStoreConfig`**, **`RerankerConfig`**). The Phase-1 clone inventory validates/adjusts this membership list.

## Prior art (why these exact shapes)

| System | What it does | What we took |
|---|---|---|
| [GEPA](https://github.com/gepa-ai/gepa) (`core/result.py`, `proposer/merge.py`) | `parents: list[list[idx\|None]]` per candidate; merge proposer emits 2-parent candidates; renders ancestry DAG | multi-parent list as the one lineage field; **improvement**: GEPA canonicalizes parent order (loses info) and stores **no per-candidate rationale** — `notes` + git ordering fill both gaps |
| Git commit model | ordered `parents`; first parent = mainline (load-bearing: `log --first-parent`); message = summary line + why-not-what body | ordering semantics; notes discipline |
| [MLflow prompt registry](https://mlflow.org/docs/latest/genai/prompt-registry/) | immutable versions with `commit_message` ("similar to Git commit messages") | immutable creation-time free-text "why" is established practice |
| [LangSmith](https://docs.langchain.com/langsmith/manage-prompts) / PromptLayer | `parent_commit_hash` + description ≤ 1,000 chars / commit message ≤ 72 chars | length caps as write discipline |
| [Windsurf memories](https://docs.windsurf.com/windsurf/cascade/memories) | `UserTriggered: bool` — explicit human ask vs agent autonomy | `origin`, and its trigger-intent (not typing-hands) semantics |
| [W3C PROV](https://www.w3.org/TR/prov-dm/) | derivation / generation / attribution as distinct relations | completeness checklist: `derived_from_ids` = derivation; `origin` = attribution; generation (evidence refs) = named v2 |
| [ARA paper](https://arxiv.org/abs/2604.24658) (arXiv 2604.24658) | exploration DAG with first-class `dead_end` nodes (hypothesis/failure-mode/lesson), `also_depends_on` convergence, 4-tag provenance; 90.2%-of-cost failure stat | motivation numbers; multi-parent confirmation; `origin` upgrade path; and a caveat baked into the `notes` description — preserved failure records can *over-constrain* future agents, so notes record observations-with-conditions, never universal rules |

## Out of scope

- The general agent memory system (Part 2 — separate project; memories will *link to* artifacts, artifacts never point at memories).
- Structured `evidence_refs` / claim→evidence bindings (named v2 follow-on, per decision 9).
- Cross-type or cross-scope lineage references, and any universal ID scheme (prose in `notes` instead; `PromptId`-style qualified unions are the precedent if this ever earns its keep).
- Lineage traversal/visualization APIs, global indexes, DAG rendering (agents walk siblings; GEPA-style tree rendering can come later).
- Backfilling provenance onto existing artifacts (legacy = `None`).
- Memory-style consolidation, expiry, or editing of provenance (immutable by design).
- Enforcing that agents *write good notes* — that's skill-library work in the O3 repo (write-discipline guidance, breadcrumb migration per decision 11).
