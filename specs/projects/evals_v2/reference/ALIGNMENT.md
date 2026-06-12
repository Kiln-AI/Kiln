---
status: complete
approved: true
signed_off: 2026-06-03
---

# Kiln Evals V2 — ALIGNMENT (decision ledger)

**Status:** ✅ **COMPLETE — signed off by Steve 2026-06-03 as the source of truth for V2 directional decisions.** All Stage 3 alignment batches (A–K) are locked; the Stage 3c consistency pass is done. Future changes are revisions (tracked with audit trail per the Revisiting note below), not new alignment.

**Frame change (2026-05-26):** This file is now the **ledger only** — ~1-paragraph entries per decision (question + locked answer + 1-paragraph rationale + blocks/unblocks + link to design file). **Implementation detail lives in `design/NN_*.md` files, not here.** See `design_dispatch.md` for the alignment-decision → design-file mapping.

Entries written before 2026-05-26 still carry their detail inline. They'll be progressively extracted into the relevant design files during Stage 4 (per `design_dispatch.md` dispatch order). New entries (from this date forward) should be skinny.

**How to read this:** Each section = one batch from `alignment_plan.md`. Each decision has the question, the locked answer, 1-paragraph rationale, what it blocks/unblocks, and a link to the design file(s) carrying the detail.

**Revisiting:** Decisions can be reopened if a later batch shows one was wrong. Reversals are tracked here with audit trail. Affected design files have their `approved` frontmatter flag flipped to `false` in the same edit.

---

## A0. Foundational principles

### A0.1. Backwards compatibility — V2 reads V1; V2 never migrates V1

**Principle:** V2 reads V1 records cleanly. V2 NEVER rewrites V1 records on disk. The risk we're guarding against: a migration sweep that batch-changes many user data files. Users have no version history on their data; no rollback if a migration corrupts something; blast radius too large.

**What this requires:**
- V2 reads V1 schemas via legacy parsing paths.
- V2 never auto-rewrites V1 files (no `model_validator`-based silent migration on load).
- V2 shapes live in additive markers/fields, gated by an explicit V2 marker (e.g. `config_type = "v2"`).
- Existing V1 records continue to load and run unchanged under V2.

**What this does NOT require:**
- V1 reading V2-only records. Mixed-version teams expect users to upgrade — the newest user pushes the project forward. V1 crashing on `config_type = "v2"` is acceptable.
- V1 supporting future V2 types or fields.
- V1 patches as a V2 launch prereq. A future patch softening V1's unknown-enum failures is nice-to-have, not blocking.

**Reference example:** [A2.1 EvalConfig V2 shape](#a21-evalconfig-v2-shape-coexistence-with-v1). V1 files load cleanly under V2 via the legacy `config_type` dispatch path. V2-only files (`config_type = "v2"`) won't load under V1 — acceptable per the framing above.

**What this rules out:**
- `model_validator`-based silent migration from V1 to V2 shape on load.
- Renaming or removing fields that V2 reads from V1.
- Schema changes that prevent V2 from loading V1 files unchanged.

**What this allows (and uses):**
- Legacy enum values stay in enums forever (`EvalConfigType.g_eval`, `EvalConfigType.llm_as_judge`) — needed for V2 to read V1.
- Legacy fields stay on models (`EvalConfig.model_name`, `EvalConfig.model_provider`) — needed for V2 to read V1.
- New typed shapes live in additive fields or unions, gated by an explicit marker (e.g. `config_type == "v2"`).
- Runner registry dispatches legacy markers to legacy adapters; V2 markers to V2 adapters.
- Composite / multi-config flows must handle both legacy and V2 children.

**Code-level facts** (verified against `~/Dropbox/workspace/kiln_new` 2026-05-21):
- `KilnBaseModel` uses Pydantic v2 default `extra = "ignore"` (no override anywhere) — V2 can add new optional fields freely; V1 silently drops unknown fields. Additive-fields strategy is safe.
- V1's `Task` uses explicit `parent_of` registration; unknown sibling folders (e.g. `eval_inputs/`) are invisible to V1. EvalInput can ship alongside TaskRun without breaking V1 child-loading.
- V1's `EvalConfigType` enum WILL raise on unknown values (e.g. `"v2"`), AND `validate_properties` at `eval.py:290-308` has an explicit `else: raise ValueError`. Both block V1 from loading V2-only configs — which is acceptable per "What this does NOT require" above.

**Scope:** Applies to every batch from A2 onward. Particularly load-bearing for A2 (EvalConfig), Batch C (cardinality / `EvalRun.dataset_id` discriminator), Batch H (V2 reads V1 implementation; explicit user-initiated V1→V2 upgrade UX if any).

---

### A0.2. Many small evals — and a builder that right-sizes datasets to input

**Principle:** A small focused eval beats either (a) no eval at all or (b) an oversized eval that times out / overfits to lookalikes. The builder must scale synthesis to the input — specific feedback gets a small targeted set; broader coverage goals get larger sets. Neither single-case unit tests nor 300-case mega-evals are acceptable defaults.

**Why:** Most Kiln users either over-spec (300 examples that time out) or under-spec (1-example "unit tests" that don't generalize). Lowering the floor for creation is a Kiln value-prop; "many small evals" is the philosophy from PROJECT.md. The right-sizing nuance prevents the principle from turning into "always default to 20."

**Application:**
- The principle stands and outlives this project (Kiln value-prop; has its own blog posts). **The specific "builder automatically right-sizes the synthetic dataset to the input" mechanism is DEFERRED out of evals V2** (see Batch G rescope) — it belongs to the future goal-first onboarding project, not the V2 infra deliverable. Recording the deferral here so the principle isn't read as a V2.0 build commitment.
- Stage 5 `design/70_builder_and_onboarding.md`: the right-sized-by-input pattern is documented as a north-star constraint for the future onboarding work, not a V2.0 create-flow feature.
- ~~Batch H decision 29 (spec builder reliability)~~: OUT OF SCOPE per H.29 (2026-06-03) — spec builder reliability is not an evals-V2 deliverable. The "right-size the synthetic set" idea remains a north-star for a future builder-reliability effort.
- ~~Batch F (feedback pipeline)~~: PUNTED 2026-06-03. "Create new eval from feedback cluster sized to the cluster" is a future-project application, not V2.0.

---

### A0.3. Config-first; code is an escape hatch IF the sandbox story closes

**Principle:** New eval functionality is expressible as config wherever it works. Config is diffable, UI-buildable, has zero execution surface, plays with Kiln's extensibility model. Code-as-eval (executable user-authored Python) is admissible only if the execution story closes acceptably.

**Gate resolved by B.13 (2026-06-03 audit note):** This principle originally framed the gate as "PyInstaller + wasmtime spike succeeds." **B.13 superseded that framing:** the locked execution story is `multiprocessing` (spawn) + `freeze_support()` + a **trust-gate UX** (crash isolation + wall-clock timeout; no WASM, no language-level sandbox — trust boundary is UX, like a coding agent's bash access). WASM is deferred to V2.x if real attack pressure emerges; no wasmtime spike is a V2.0 prereq. So the gate is met — `code_eval` ships (B.12) — but via accepted-trust + crash-isolation, not full containment. Read B.13 for the actual model; the "wasmtime spike" language here is historical.

**Why:** Config-driven evals are auditable, shareable across teams, plug into the V2 builder UX, and have zero execution-attack surface. Code-as-eval introduces sandboxing risk that's still genuinely open. Treating config as first-class avoids the trap of "we'll just give users a Python escape hatch" — which leads to thin config investment and unreviewable user code.

**Application:**
- Batch B (code vs config + sandboxing) — the directional decision. A0.3 is the principle; Batch B locks the specific outcome (config-only / code-with-sandbox / hybrid). Hybrid is NOT the default answer.
- A2.4 V2 EvalConfigType catalog: code-shaped types (`code_eval`, complex `event_ordering`) are conditional on Batch B.
- Batch G builder UX: config-first defaults; code is a power-user surface (if shipped at all).
- Stage 5 `design/27_type_code_eval.md`: only writes if Batch B picks code or hybrid.

---

### A0.4. Local-first; PyInstaller bundle stays clean

**Principle:** Kiln runs locally. The PyInstaller-bundled distribution is sacred. Anything that materially bloats it (e.g. ~20 MB for wasmtime) or pulls runtime dependencies (e.g. pip-install at runtime) requires explicit budget approval as a tradeoff.

**Why:** Local-first is Kiln's positioning — privacy, latency, no cloud lock-in, works offline. Bundle bloat erodes the developer experience and slows adoption. Runtime dependency fetching breaks the "works without setup" promise.

**Application:**
- Batch B sandboxing decision: if WASM/wasmtime adds ~20 MB, that's an explicit budget decision, not a free design choice. PyInstaller + wasmtime spike outcome feeds into this.
- Builder UX (Batch G): spec builder's `api.kiln.tech` dependency conflicts with local-first; offline fallback strongly preferred. Flagged for Batch G design.
- Stage 6 Phase 5 (`code_eval`): gated by sandboxing decision AND bundle-budget acceptance.

---

### A0.5. Feedback closes the loop

**Principle:** Feedback is not a write-only journal. Every feedback item is an entry point into the eval pipeline — assign to an existing eval, derive a new EvalInput, promote corrected output to reference data, or explicitly mark won't-fix. "I see a bug, just flag it" produces eval signal, not buried text.

**Why:** V1 has a `Feedback` model that's captured but never consumed — pure waste. V2's feedback pipeline is the biggest differentiator opportunity (no competitor closes this loop fully). It's also Kiln's answer to the "users don't have data" problem from PROJECT.md — feedback IS data.

**Application (updated 2026-06-03 — Batch F punted):** A0.5 survives as a **north-star direction only**; its implementation is owned by a future standalone Feedback Pipeline project, not evals V2.0. The bullets below describe that future project, not V2.0 deliverables:
- ~~Batch F (feedback pipeline + triage)~~ — PUNTED 2026-06-03 to a future project. See Batch F section.
- ~~F.1 / F.2~~ — UN-LOCKED 2026-06-03 (deferred). `EvalInput` ships in V2 **without** `source_task_run_id`; snapshot/source-linkage semantics are the future project's to design.
- ~~`design/60_feedback_and_triage.md`~~ — out of scope for evals V2 (see `design_dispatch.md`).
- ~~Stage 6 Phase 4~~ — moved out of the V2 roadmap (see PLAN.md Phase 4).

---

### A0.6. "Doesn't exist today" is design space, not a gap to patch

**Principle:** When a capability doesn't exist in Kiln V1, the right response is "design what should exist," not "patch the gap." V2 is allowed (and expected) to invent. Framing missing pieces as gaps narrows ambition and re-anchors on V1's constraints.

**Why:** Several V2 concepts have no V1 precedent: EvalInput as separate entity, structured per-config reference data, feedback-to-eval pipeline, goal-first builder. Framing these as "what's missing from V1" leads to minimal additions that preserve V1's defaults. Framing them as "design what should exist" leads to better-shaped designs.

**Application:**
- Stage 5 design docs: write the V2 design fresh, not as a delta against V1. Reference V1 only where coexistence is required (per A0.1).
- Sub-agent dispatches: frame the brief as "design X for V2," not "what's the V1 gap and how do we fix it."

---

## Batch B — Strategic direction: code vs config + sandboxing (in progress)

### B.12. Hybrid — config-first, code as additional EvalConfigType

**Decision:** V2 ships **config-first with `code_eval` as one additional EvalConfigType among many**. The config DSL + typed built-in catalog handles the common cases (and most uncommon ones, by adding new built-in types over time). `code_eval` exists for the long-tail expressiveness gap — user-authored Python scorer code, gated by sandbox + trust UX.

**Why not config-only:** A2.4 already locked the V2.0 config catalog. There are real eval categories (output grounding with domain knowledge, stateful trace analysis, per-project custom logic) where "add another typed built-in" doesn't scale. Code is a manageable escape hatch.

**Why not code-only:** LLM-as-judge (and most config types) is naturally config-shaped. Code-only would lose the UI-buildable, diffable, battle-tested, shareable advantages of config — the things Steve called out: "Config has more tests, more battle tested, we can build nice UI around it. Common patterns get a type and can be config driven."

**Architectural impact:** None on the broader V2 design. `code_eval` is `V2EvalType.code_eval` with a `CodeEvalProperties` Pydantic class, plugged into the V2 adapter registry (A2.11) via a `CodeEvalAdapter` (subclass of `BaseEval`). Schema design, EvalInput, runner architecture, filter pipeline, and builder are unaffected. The only design surfaces that touch code_eval specifically are: (a) sandboxing tech (B.13), (b) trust-gate UX, (c) PyInstaller bundling, (d) properties shape (inline code string vs file reference vs import path — Stage 5 design work).

**Position in catalog:** `code_eval` ships in V2.0 as one of the 8 launch EvalConfigTypes (per B.12 + A2.4). Gate resolved by B.13 — execution model is `multiprocessing` (spawn) + trust-gate UX; no WASM spike required. Slotted as PLAN.md Phase 5 (after Phases 1-4).

**Application of A0 principles:**
- [A0.3](#a03-config-first-code-is-an-escape-hatch-if-the-sandbox-story-closes) Config-first — preserved. Code is escape hatch.
- [A0.4](#a04-local-first-pyinstaller-bundle-stays-clean) Local-first + bundle clean — the ~20MB sandbox cost is an explicit budget acceptance, not a free design choice. Subject to spike + budget approval.
- [A0.6](#a06-doesnt-exist-today-is-design-space-not-a-gap-to-patch) Design space — code_eval as a deliberate, designed EvalConfigType (not a "gap patch") fits this framing.

**Unblocks:** B.13 sandboxing tech choice (the next decision). Stage 5 `design/27_type_code_eval.md` (un-strikes from PLAN.md Stage 5 list). Plugin extensibility (Batch E #36) — the contract has two extensibility dimensions: third-party-typed-EvalConfigTypes AND user-authored-code-per-project.

**Linked decisions:**
- B.13 — sandboxing tech: **locked as in-process `exec()` with trust-gate UX (no sandbox)**. See B.13 below.
- B.14 — `event_ordering` form: deferred per A2.4; if revisited, host on `code_eval`. See B.14 below.
- Trust-gate UX — separate design concern (Stage 5 or Batch G builder UX).

---

### B.13. `code_eval` execution model — `multiprocessing` (spawn) + `freeze_support()` + trust-gate UX

**Decision:** `code_eval` runs user Python in a **`multiprocessing.Process` child started in `spawn` mode**, dispatched via Python stdlib's officially-supported `multiprocessing.freeze_support()` pattern for PyInstaller. A thin worker module hosts the target function; user code runs via `exec()` inside that worker. Wall-clock timeout via `p.join(timeout=...)` then `p.kill()` (cross-platform). Resource caps via `resource.setrlimit` on Unix (P2 — cut if any complexity). Windows: no rlimits enforced. Trust boundary remains **UX-only** — a per-project "do you trust this project's code evals?" prompt before any execution. Security model is the user accepting responsibility, same as accepting a coding-agent's bash access.

**Why this superseded the earlier in-process `exec()` lean:** the multiprocessing path eliminates the PyInstaller complexity that drove the original argument against subprocess (manual argv-flag dispatch, manual IPC string-passing, full Kiln bootloader cold start). PyInstaller's runtime hook (`pyi_rth_multiprocessing.py`) intercepts spawned children before Kiln `main()` runs; pickling provides type-safe IPC; thin-worker-module discipline keeps child cold start at 50-150ms. Verified against the [official PyInstaller multiprocessing docs](https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html#multi-processing). For "small complexity cost," the win is crash isolation + (Unix) runaway protection + wall-clock cancellation — strictly better than in-process `exec()`.

**What this enforces:**
- **Crash isolation (all platforms):** segfault / fatal C-extension crash / hard kill in user code does not take down Kiln.
- **Wall-clock timeout (all platforms):** `p.join(timeout=X)` + `p.kill()` bounds eval execution time regardless of OS.
- **Runaway CPU/memory caps (Unix only, P2):** `resource.setrlimit(RLIMIT_CPU, RLIMIT_AS)` in worker before `exec()`. Cut if any complexity.
- **Trust boundary (UX only):** per-project consent gate before execution.

**What this does NOT enforce:**
- Network access — wide open. User code can `requests.get(...)`. No network sandbox.
- Filesystem path restrictions — wide open. User code can read `~/.ssh/`, write anywhere the user can.
- Windows: no kernel-level CPU/memory caps. Crash isolation + wall-clock timeout still work.
- Language-level escapes — N/A (no language-level sandbox; nothing to escape).

**Why this option over alternatives (updated):**

| Option | Verdict |
|---|---|
| **In-process `exec()`** | Was leading candidate (rejected by Steve in favor of multiprocessing). Pros: trivial. Cons: no crash isolation, no runaway protection, buggy code_eval takes Kiln down mid-batch. Multiprocessing wins for small complexity cost. |
| **Manual subprocess (self-reinvocation + argv flag)** | Real PyInstaller hoops — was the framing that drove us toward in-process exec. Multiprocessing+freeze_support is the *officially supported* version of this pattern with no manual dispatch / IPC strings. Verdict: rejected in favor of multiprocessing. |
| **WASM Python (wasmtime + own wrapper)** | Strongest technical sandbox + network/FS blocking. Costs: ~20 MB bundle (A0.4 budget hit), PyInstaller + wasmtime spike risk (no documented prior art), 2-3s cold start, pure-Python-only DX restriction, ongoing maintenance of own wasmtime host glue (`llm-wasm-sandbox` is a 2-star one-person project — not safe to depend on). Verdict: deferred to V2.x if real attack pressure emerges. |
| **OS-level sandbox (seccomp/Seatbelt/AppContainer DIY)** | Three OS code paths; macOS Seatbelt deprecated since 2016; Windows AppContainer hostile to arbitrary process sandboxing. Verdict: rejected. |
| **`@anthropic-ai/sandbox-runtime`** | npm package; no guaranteed Node env in PyInstaller bundle. Verdict: rejected. |
| **RestrictedPython** | Per its own docs not a sandbox; per PEP 551 "do not attempt to implement a sandbox within the Python runtime." Not a quality issue — fundamental design impossibility (Python introspection escapes). Verdict: rejected. |
| **AST import allowlist** | Same fundamental problem (`__builtins__['__import__']`, `().__class__.__mro__[1].__subclasses__()` escape import gating). Verdict: punted by Steve. |

**Architecture sketch:**

```python
# kiln/eval/sandbox_worker.py — THIN module. Imports ONLY stdlib + Pydantic.
# No UI framework, no DB layer, no model registry, no `from kiln.X` imports
# beyond explicit narrow type-only ones (enforced by lint / CI / convention).
import multiprocessing
import resource  # Unix only — guard at usage

def _execute_scorer(code: str, inputs: dict, limits: dict, result_queue):
    try:
        # P2: rlimits on Unix. Cut if any complexity arises in implementation.
        if hasattr(resource, "RLIMIT_AS") and limits.get("mem"):
            resource.setrlimit(resource.RLIMIT_AS, (limits["mem"], limits["mem"]))
        if hasattr(resource, "RLIMIT_CPU") and limits.get("cpu"):
            resource.setrlimit(resource.RLIMIT_CPU, (limits["cpu"], limits["cpu"]))
        # NOTE (2026-06-05): scorer contract refined by design_phase_calls.md C2.
        # The real worker compiles the user code, then CALLS a `def score(output,
        # trace, reference_data, task_input, kiln) -> dict[str, float]` function and
        # uses its explicit return — NOT a magic `result` var harvested from the
        # namespace. The exec/Queue mechanics below are illustrative; authoritative
        # scorer contract + worker in design/27_type_code_eval.md sections 2 + 4.
        ns = {}
        exec(code, ns)
        result_queue.put({"ok": ns["score"](**inputs)})
    except Exception as e:
        result_queue.put({"error": str(e)})

def run_scorer(code: str, inputs: dict, limits: dict, timeout: float):
    q = multiprocessing.Queue()
    p = multiprocessing.Process(target=_execute_scorer, args=(code, inputs, limits, q))
    p.start()
    p.join(timeout=timeout)
    if p.is_alive():
        p.kill()
        p.join()
        raise TimeoutError("Scorer exceeded wall-clock limit")
    if p.exitcode != 0 and q.empty():
        raise RuntimeError(f"Scorer crashed (exit code {p.exitcode})")
    return q.get_nowait()

# kiln/__main__.py (or equivalent entry point)
import multiprocessing
if __name__ == "__main__":
    multiprocessing.freeze_support()  # MUST be first line per official docs;
                                       # before argv parsers, GUI framework init, heavy imports.
    # ... rest of Kiln startup. Child process is intercepted by PyInstaller's
    # runtime hook and never reaches this code.

# CodeEvalAdapter (Stage 5 design)
class CodeEvalAdapter(BaseEval):
    def run_eval(self, eval_input: EvalInput) -> Score:
        if not project_trust_granted(self.project):
            raise CodeEvalNotTrustedError(...)
        result = run_scorer(
            code=self.eval_config.properties.code,
            inputs=build_eval_inputs(eval_input),
            limits={"cpu": 30, "mem": 512 * 1024 * 1024},  # tunable
            timeout=60.0,
        )
        if "error" in result:
            return Score.failed(reason=result["error"])
        return Score.from_user_result(result["ok"])
```

**Linux start-method note:** Linux defaults to `fork`. On Linux, must explicitly set `multiprocessing.set_start_method("spawn")` (Python 3.14+ will change the default). macOS + Windows default to `spawn`.

**Trust-gate UX (separate design — Stage 5 or Batch G):**
- "Do you trust this project's code evals? They run as you, with your filesystem and network access." prompt before first execution per-project.
- Persist consent per-project (file marker in project dir or app DB).
- Clear "this runs in Kiln with your access" framing — honest about scope.
- Mirror VS Code workspace trust, npm `--ignore-scripts`, Claude Code's permission model.

**Phase 5 implementation budget:**

1. `kiln/eval/sandbox_worker.py` — thin module with `_execute_scorer` + `run_scorer`. Lint/CI rule preventing heavy Kiln imports.
2. `freeze_support()` wired as first line of main entry point.
3. `multiprocessing.set_start_method("spawn")` on Linux startup path.
4. rlimits on Unix (P2 — only if simple; cut otherwise).
5. Windows: no rlimits, wall-clock timeout + crash isolation are sufficient.
6. `CodeEvalAdapter` wiring through the V2 adapter registry (A2.11).
7. Trust-gate UX (separate design / Batch G).
8. Error capture / Queue protocol / serialization of result types.
9. Eval helper library injected into worker namespace (Stage 5 design).
10. Light spike at Phase 5 start: validate cold-start time on actual Kiln-sized bundle (50-150ms target); validate `spawn` start method works in PyInstaller on all three OSes.

**Honest gotchas (documented for Phase 5):**

1. **Worker-module hygiene** — if `sandbox_worker.py` ever gains a transitive import of heavy Kiln modules (even via a `from kiln.models import X` type hint at module level), child cold start silently balloons to 500ms+. Enforce via lint rule and PR review convention.
2. **Pickling constraint** — `_execute_scorer` must be a module-level named function. No closures, lambdas, or locally-defined targets. Arguments (code string, dict, Pydantic model, Queue) must all be picklable.
3. **Stdout / stderr in windowed PyInstaller builds** — child has `sys.stdout = None` in `--windowed` / `--noconsole`. Naive `print()` from user code will crash. Redirect or wrap in the worker.
4. **Logging in child** — config not inherited via spawn. Re-init in worker if needed.
5. **spawn thread-safety on Linux PyInstaller** ([Issue #7410](https://github.com/pyinstaller/pyinstaller/issues/7410)) — concurrent spawns from multiple threads can fail. Serial eval execution is fine; parallel runs need a spawn lock.

**Reversibility:**
- If real attack pressure emerges (popular shared-Kiln-project compromise), V2.x can swap `multiprocessing` for a WASM-based execution under the same `CodeEvalAdapter` surface.
- If Windows users hit runaway-code issues, V2.x can add `pywin32` Job Objects for Windows rlimits.
- Architecture doesn't preclude either upgrade — `CodeEvalAdapter` + `run_scorer` are the seams.

**Unblocks:** `code_eval` design (Stage 5 `design/27_type_code_eval.md` — properties shape including code-string vs file reference vs import path, eval helper library surface, scorer contract, Queue serialization protocol, error handling). PLAN.md Phase 5 scope (multiprocessing wiring + thin worker module + trust-gate UX + helper library — no language-level sandbox infrastructure).

**Application of A0:**
- A0.3 — config-first preserved; code is escape hatch.
- A0.4 — bundle stays clean (0 MB overhead; multiprocessing is stdlib).
- A0.6 — designing trust-gate UX as a first-class V2 surface, not a half-measure sandbox.

**Closes BLOCKER opens:**
- "Code vs config for new eval types" — resolved (hybrid; code as `code_eval` EvalConfigType per B.12).
- "PyInstaller + wasmtime bundling unvalidated" — no longer a V2 blocker (WASM deferred to V2.x; no spike needed for V2.0).
- "`llm-wasm-sandbox` maturity" — N/A (we're not using it).
- "Cold start mitigation for WASM" — N/A (no WASM).
- "Kiln PyInstaller bundle size budget for WASM" — N/A (no WASM overhead).
- "Config DSL design" — re-scoped: not a sandbox replacement, but still a real design surface for built-in EvalConfigTypes (Stage 5 per-type design docs).

---

### B.14. `event_ordering` form — deferred; if revisited, host on `code_eval`

**Decision:** `event_ordering` is deferred to post-V2 per A2.4. No DSL or built-in type ships in V2.0. If/when revisited:

- **Default host:** Write the event-ordering check as user Python in `code_eval` (now that `code_eval` is in V2 per B.12 + B.13). No separate event-ordering DSL needs to be invented preemptively.
- **Promotion path:** If real usage patterns prove out a common shape (e.g. `event_type(pattern) BEFORE event_type(pattern)` repeated across many projects), a typed `event_ordering` built-in EvalConfigType can be added at that point. Design driven by real usage, not pre-emptive.

**Why this collapses cleanly:** B.12 locked code_eval as a real V2 EvalConfigType. That gives users a generic escape hatch for any expressiveness gap including event-ordering. The previous tension ("does event_ordering need a DSL or code?") dissolves — code is now an option for all such cases, and the DSL question becomes "is this pattern common enough to deserve a built-in?" which is a post-launch usage question.

**Closes open:** "Event-ordering DSL feasibility" — no longer a V2 blocker. If/when revisited, design from usage data, not pre-emptive analysis.

---

## Batch A1 — EvalInput + reference data shape

### A1.1. EvalInput field placement + per-variant input naming

**Decision:** Lift turn-agnostic fields to the top-level `EvalInput`; keep only turn-shape-specific fields inside the discriminated `EvalInputData` variants. Each variant names and types its input field semantically (no shared `ContentProperties` abstraction).

**Naming note:** The discriminated payload is named `EvalInputData` (not `EvalInputProperties`). The variants ARE the input data — for `MultiTurnSyntheticEvalInputData`, the synthetic dialogue is the payload, not metadata about it. "Properties" wrongly implied "metadata about input." Field on `EvalInput` is `data:` (not `properties:`).

**Shape:**

```python
class EvalInput(KilnParentedModel):
    tags: list[str] = []                              # universal
    reference: dict[str, JsonValue] | None = None    # universal — see A1.2
    data: EvalInputData                               # discriminated; turn-specific only

class UserMessage(BaseModel):
    text: str
    # future: attachments, images-in-chat, etc.

class SingleTurnEvalInputData(BaseModel):
    type: Literal["single_turn"] = "single_turn"
    user_message: UserMessage

class MultiTurnSyntheticEvalInputData(BaseModel):
    type: Literal["multi_turn_synthetic"] = "multi_turn_synthetic"
    # Optional seed. UI always sets this; power users may leave None for a
    # purely synthetic conversation (synthetic user generates turn 1 from
    # persona / goal / policy). When set, synthetic user takes over from turn 2.
    first_message: UserMessage | None = None
    synthetic_user_info: SyntheticUserInfo    # shape locked in Batch C
```

**Rationale:**
- `tags` and `reference` are turn-agnostic — same shape, same semantics across all variants. Lifting them to top level removes duplication and gives one place to look for ground-truth / filtering metadata.
- Input data IS turn-shape-specific. A chat message, an image-gen prompt, and a classifier input record don't share a meaningful abstraction. Naming the input field per variant (`user_message`, `first_message`, future `prompt` / `input_record`) is more readable than a generic `content: ContentProperties`.
- `ContentProperties` as a concept is dropped. Modality extensibility happens through new variants or by extending `UserMessage` with attachments, not through a content-level discriminator.
- `SingleTurnEvalInputData` is nearly empty for V2.0 — that's fine. It's a typed slot for future single-turn-only fields and preserves the discriminator tag.
- Naming chosen over `EvalInputProperties` because the variants carry input data (e.g. synthetic dialogue), not metadata about the input. Shape determines runtime path 1:1 — that's fine and not a separate axis.

**Unblocks:** EvalInput Pydantic model is fully specified for V2.0. Future variants (image-gen, classifier, etc.) add themselves with their own input field naming, no migration of the shared abstraction.

**Resolved sub-decision:** `first_message: UserMessage | None = None` (optional). UI always sets it on eval creation; power users may leave it `None` for purely synthetic conversations where the synthetic user generates turn 1 from persona / goal / policy. When set, the synthetic user takes over from turn 2.

---

### A1.2. `reference` shape

**Decision:** `EvalInput.reference: dict[str, JsonValue] | None` — flat dict at the top level of EvalInput (universal across all turn types). JSON-roundtrippable values only. Root must be a dict or None — top-level non-dict values (array, string, bool) are rejected because they would break key-based config consumption. EvalConfigType implementations are responsible for typechecking the reference keys they consume (declare expected keys + types, fail fast at bind time).

**Specifics:**
- Use Pydantic v2's built-in `JsonValue` type for value validation. Value alias: `None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]`.
- First-party EvalConfigType implementations get `ty`-enforced typechecking on the reference keys they read. Third-party plugins inherit the same contract.

**Rationale:** A flat dict scales better to a growing catalog of EvalConfigTypes (a shared typed schema would get brittle as types are added), supports third-party EvalConfigTypes cleanly without schema migration, and gives up only IDE autocomplete on reference data — recoverable through the EvalConfigType-declared key contract.

**Trade-offs accepted:**
- No EvalInput-creation-time validation of reference shape — validation happens at config-bind time.
- Builder UX has more work to do: it must introspect each selected EvalConfig's declared reference keys to render a reference-data form. (Tracked for Batch G.)

**Unblocks:** EvalInput Pydantic model is fully specified. Per-config reference-key declaration becomes the contract for EvalConfigType authors.

---

### A1.3. Multi-config-per-input reference data

**Decision:** Flat on `EvalInput.reference`. Each EvalConfig declares which keys it consumes. Validation at config-bind time, not schema time.

**Rationale:** Pairs naturally with A1.2 — a single bag of reference data, configs pick what they need. Namespacing by `eval_config_id` would tightly couple datasets to specific configs (painful for shared datasets and config reorganization). Hybrid was two patterns for a problem the flat approach already solves.

**Unblocks:** Multi-config-per-input scoring (the core V2 multi-score story). Composite scoring across configs. Dataset sharing across evals.

**Consequence opens** (added to `OPENS.md`):
- Eval skips / missing reference data — runner contract when a config's required reference keys are absent.
- Reference-key collision warning — when two configs on the same Eval declare the same reference key.
- Naming guidelines for reference keys — generic names like `judge_criteria` invite collisions; prefer EvalConfigType-prefixed names (`llm_as_judge_criteria`). Update CR/sub-agent conventions.

---

### A1.4. Per-case criteria on EvalInput vs global on EvalConfig

**Decision:** No separate `criteria` field on EvalInput. Per-case variation in checks is expressed through reference data parameters that EvalConfigs opt to consume. Global checks (the "12 things this eval cares about") live on EvalConfigs.

**Rationale:** Kintsugi's "per-case criteria" pattern decomposes cleanly into the already-locked A1.2/A1.3 mechanism:
- Per-case **selection** of typed checks → either model each as its own EvalConfigType with a typed reference field, or expose a `reference["check_names"]: list[str]` for a single config to dispatch from a registry.
- Per-case **content** for judge criteria → store as `reference["llm_as_judge_criteria"]: list[str]`, consumed by an enhanced `llm_judge` EvalConfigType that runs per-criterion verdicts.

**Preserves:** The Eval-as-dashboard model. Each EvalConfig produces a score; per-case variation lives in reference data, not in a separate criteria stream. GEPA / optimizer integration works because they target Eval-level scores.

**Gives up:** Expressing "this eval has 5 global checks PLUS case 47 has 3 extra checks." If you need that, the answer is to spin off case 47 into its own eval (consistent with "many small evals" philosophy).

**Unblocks:** EvalInput Pydantic model is fully specified — no criteria field required. CriterionSpec is internal to specific EvalConfigType implementations.

**Linked open:** Enhanced `llm_judge` per-input criteria support (added to OPENS.md). The design of how `llm_judge` consumes per-case criteria lives in Stage 5 `design/21_type_llm_judge.md`.

---

### A1 — confirmations and notes

- **`SyntheticUserInfo` stays typed.** Flat-dict design applies to `reference` only. `synthetic_user_info` remains its own versioned Pydantic model on `MultiTurnSyntheticEvalInputData` (shape decision deferred to Batch C, joint with parallel multi-turn project).
- **`EvalInput` discriminator structure is open for extension.** Future variants (image-gen, classifier, etc.) add themselves to `EvalInputData` with their own input field naming. The universal fields (`tags`, `reference`) apply.

---

## Batch A2 — EvalConfig discriminated union + judge unification (in progress)

### A2.1. EvalConfig V2 shape (coexistence with V1)

**Decision:** EvalConfig adds a new `v2` value to the existing `EvalConfigType` enum. For `config_type = "v2"`, `properties` is a typed discriminated union (inner `type` field discriminates). For legacy values (`g_eval`, `llm_as_judge`), `properties` stays as the V1 untyped dict and root fields (`model_name`, `model_provider`) remain populated. This is the reference application of [A0.1 backwards compatibility](#a01-backwards-compatibility--v2-is-additive-v1-is-preserved).

**Reference implementation:**

```python
class EvalConfigType(str, Enum):
    # Legacy — kept for backwards compat with V1 files on disk.
    # New configs always use v2; the actual eval type lives in properties.type.
    g_eval = "g_eval"
    llm_as_judge = "llm_as_judge"
    # V2 marker. Inner properties.type carries the actual V2 type.
    v2 = "v2"


class EvalConfig(KilnParentedModel):
    name: str
    description: str | None = None
    config_type: EvalConfigType

    # Legacy root fields — populated for legacy config_types, None for v2.
    # Kept at root so V1 files load unchanged.
    model_name: str | None = None
    model_provider: str | None = None

    # Properties shape depends on config_type:
    # - legacy (g_eval / llm_as_judge): untyped dict, as V1 stored it
    # - v2: typed discriminated union (inner `type` is the discriminator)
    properties: V2EvalConfigProperties | dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_shape(self):
        if self.config_type == EvalConfigType.v2:
            assert isinstance(self.properties, BaseModel), "v2 requires typed properties"
            assert self.model_name is None and self.model_provider is None
        else:
            assert self.model_name is not None and self.model_provider is not None
        return self


# V2-only type enum, separate from EvalConfigType. Only grows with new V2 types.
# Plugin extensibility (Batch E #36) adds to this enum.
class V2EvalType(str, Enum):
    llm_judge = "llm_judge"
    exact_match = "exact_match"
    pattern_match = "pattern_match"
    set_check = "set_check"
    tool_call_check = "tool_call_check"
    contains = "contains"
    composite = "composite"
    # ... etc per the type catalog


class LlmJudgeProperties(BaseModel):
    type: Literal[V2EvalType.llm_judge] = V2EvalType.llm_judge
    model_name: str
    model_provider: str
    eval_steps: list[str]
    g_eval_mode: bool = False
    # ... enhanced fields (per-criterion verdicts, trace condensation, reference templating)


class ExactMatchProperties(BaseModel):
    type: Literal[V2EvalType.exact_match] = V2EvalType.exact_match
    field_path: str          # where in trace/output to read
    reference_key: str       # which key in EvalInput.reference to compare against


# ... other V2 properties classes per the type catalog


V2EvalConfigProperties = Annotated[
    Union[
        LlmJudgeProperties,
        ExactMatchProperties,
        PatternMatchProperties,
        SetCheckProperties,
        ToolCallCheckProperties,
        ContainsProperties,
        CompositeProperties,
        # ... etc
    ],
    Discriminator("type"),
]
```

> **Snippet is illustrative, not canonical (note added 2026-06-05).** This early sketch predates several locked decisions and is intentionally not kept field-accurate — the design files own the real shapes. Specifically: the `V2EvalType` enum here is partial and stale (the canonical V2.0 catalog is **8 types** per [A2.4](#a24-lean-eval-type-catalog-for-v20) as amended by J.38 — it adds `step_count_check` + `code_eval` and **defers `composite`** to post-V2; `composite`/`CompositeProperties` appear above only as an illustration of the union pattern). Field names are also historical: `g_eval_mode` → `g_eval`, `field_path` → `value_expression`, and `eval_steps` is folded into the judge prompt design. Authoritative: `design/10` (schemas), `design/20` (catalog), `design/21` (judge), `design/22` (deterministic types).

**Two discriminator mechanisms doing different jobs:**
- **Outer:** `config_type` on EvalConfig — a marker (not a Pydantic discriminator) that drives a `model_validator` to pick legacy vs V2 parsing. Plain field, plain validator.
- **Inner:** `type` on each V2 properties variant — the standard Pydantic v2 `Annotated[Union[...], Discriminator("type")]` pattern. Works on Python 3.10+ with Pydantic v2.

**How V1 / V2 clients interact with each file shape:**

| File on disk | V1 Kiln client | V2 Kiln client |
|---|---|---|
| V1 EvalConfig (`config_type ∈ {g_eval, llm_as_judge}`) | Loads cleanly. Runs via existing adapters. ✓ | Loads via legacy parsing path (properties as dict, root model fields populated). Dispatches to legacy adapter. ✓ |
| V2 EvalConfig (`config_type = "v2"`) | `v2` is an unknown enum value. Old client should skip with warning (V1 patch may be required to make this graceful — open for Batch H). | Loads via V2 parsing path. Properties validated as the V2 discriminated union. Dispatches to V2 adapter registry keyed on `properties.type`. ✓ |

**Naming:** `"v2"` as the marker name matches user-facing language ("Evals V2"). If V3 ever happens we'll address it then.

**Unblocks:** Every V2 EvalConfigType (the ~13 from the catalog) is expressible as a `V2EvalConfigProperties` variant. Plugin extensibility contract (Batch E #36) adds new variants to the union and new values to `V2EvalType`. Phase 0 schema migration is now additive only — no rewriting of existing data.

**Linked opens** (for Batch H):
- V1 reading V2 files — V1 currently fails (verified: enum raise + explicit `else: raise` in validate_properties). Acceptable per A0.1; optional future V1 patch is nice-to-have.
- User-initiated "convert this eval to V2 format" action — is there one? Default: no auto-convert, explicit only. If yes: overwrite-in-place vs create-alongside?
- Composite configs mixing V1 and V2 children — works as long as runner dispatches both. Worth explicit test coverage.
- Eventual deprecation of legacy shape — probably never within V2 lifetime. Post-V2 placeholder.

---

### A2.2. Unify `g_eval` and `llm_as_judge` under V2 `llm_judge` with `g_eval_mode: bool` flag

**Decision:** V2 ships a single judge type — `V2EvalType.llm_judge`. `LlmJudgeProperties` carries a `g_eval_mode: bool = False` field that toggles between the two scoring modes (G-Eval token-log-probs over rating tokens; standard structured-output). Both legacy V1 enum values (`EvalConfigType.g_eval`, `EvalConfigType.llm_as_judge`) stay in the enum forever and continue to dispatch to the legacy `GEval` adapter unchanged — V2 reads V1 files without converting them (per [A0.1](#a01-backwards-compatibility--v2-reads-v1-v2-never-migrates-v1)).

**Field-name note (2026-06-03):** The implementation field name is **`g_eval: bool`** per the Batch D design file (`design/40_template_and_extraction.md` §3.1, renamed from the `g_eval_mode` used in early A2.1/A2.2 sketches). The design file is authoritative for the final name; the `g_eval_mode` spelling in this section's prose and the A2.1 reference snippet is historical.

**Why a bool, not an enum:** Two modes today (G-Eval vs structured output). A bool is the simplest schema that expresses the choice. If a third mode (e.g. constrained-decoding) ever arrives, migrating bool → enum is additive within `LlmJudgeProperties`.

**Why no auto-upgrade of V1 evals:** V1 `g_eval` configs stay V1 forever. If a user wants V2 `llm_judge` features (per-criterion verdicts, trace condensation, reference templating), they create a new V2 EvalConfig alongside the V1 one. No silent rewrite; explicit-only conversion UX would be a separate decision (currently no plans).

**Naming:** `llm_judge` matches the V2 catalog's snake_case convention and is the name already used consistently in V2_PITCH.md, _synthesis.md, and prior alignment sections.

**Unblocks:** V2 type catalog (A2.4) has exactly one judge type. Stage 5 `design/21_type_llm_judge.md` writes one enhanced judge design, with `g_eval_mode` as one of several toggles alongside per-criterion verdicts, trace condensation, reference templating. Plugin extensibility (Batch E #36) extends one judge type.

**Linked open** (Batch H 32a): How the V2 `llm_judge` adapter and legacy `GEval` adapter share LLM-call / prompt-construction / score-parsing code. The unification at the *type* level (this decision) is orthogonal to how implementation code is reused — the latter is Batch H scope.

---

### A2.3. `evaluation_data_type` becomes per-EvalConfig in V2; legacy field made optional on Eval

**Decision:** The V1 `Eval.evaluation_data_type` enum field is changed from required (V1: `EvalDataType = EvalDataType.final_answer`) to optional (V2 definition: `EvalDataType | None = None`). V2-only Evals set it to `None`. V2 EvalConfigTypes declare what data they consume in their own properties (per type, no shared abstraction). The legacy Eval-level field is preserved for V1 EvalConfigs (which continue to read it from the grandparent Eval unchanged).

**Schema:**

```python
class Eval(KilnParentedModel):
    # ... existing fields ...

    # LEGACY (V1). Required field on V1 clients; optional in V2 definition.
    # V1 EvalConfigs (g_eval, llm_as_judge) read this from the grandparent Eval
    # to know whether to receive final_answer / full_trace / reference_answer.
    # V2 EvalConfigs declare their own data needs in properties (per A2.3) and
    # set this to None. V1 clients reading a V2-only Eval will fail on the
    # missing required field — this is acceptable per A0.1 (mixed-version teams
    # upgrade laggards).
    evaluation_data_type: EvalDataType | None = None
```

**For V1 clients:** Read paths unchanged. The field is still treated as required by V1 client code (compiled against the V1 class definition). V1 will fail to load a V2-only Eval (`evaluation_data_type: None`) — acceptable per [A0.1](#a01-backwards-compatibility--v2-reads-v1-v2-never-migrates-v1).

**For V2 clients:** V2 EvalConfigTypes declare their data needs in their own properties. *(Originally sketched as a `LlmJudgeProperties.data_source` field; superseded by Batch D — the judge's data needs are now expressed via its Jinja2 `prompt_template` + `required_var` expressions per D.2/D.3, and simple-check types via `value_expression`. The principle below is unchanged: per-config, not Eval-level.)* The runner extracts per-config based on properties, not via a single Eval-level extraction pass. This unlocks long-standing V1 Pain Point 6 — one Eval can mix an LLM-judge config reading `full_trace` and an exact-match config reading a specific field path.

**For mixed-config Evals (V2 EvalConfig under a V1-shaped Eval, or vice versa):** A V2 EvalConfig dropped into a V1 Eval ignores `evaluation_data_type` and reads its own properties. A V1 EvalConfig under a V2-shaped Eval still reads `evaluation_data_type` from the grandparent (legacy adapter behavior unchanged) — which means a V2-shaped Eval (with `evaluation_data_type = None`) containing a V1 EvalConfig is invalid and should be rejected at bind time. (Practical impact minimal: you wouldn't create a V1 EvalConfig under a V2 Eval; V1 EvalConfigs are read-only legacy.)

**No shared data-extraction abstraction in V2.0** (per-properties only, not a base `DataSelector` field). The right-level coupling for V2.0 — premature abstraction otherwise. **Note:** Batch D (filter pipeline shape) may introduce filter primitives that **layer** on top of per-type data extraction (helper/extension), not replace it. Revisit interaction with this decision when Batch D lands.

**Linked open (existing):** `EvalRun.validate_output_fields` V2 bypass — the validator at `eval.py:146-166` reads `evaluation_data_type` from the grandparent Eval to gate `task_run_trace`/`reference_answer` presence on `EvalRun`. For V2 EvalRuns, this validator needs to bypass cleanly. Phase 0 sub-task 3 (EvalRun model extension) implements; design is in `OPENS.md`.

**Unblocks:** V2 type catalog (A2.4) — each type can declare its data shape. V2 runner architecture (Batch C) — per-config data extraction. Stage 5 `design/45_runner_architecture.md` and per-type design docs.

---

### A2.4. V2 EvalConfigType catalog — V2.0 launch surface (lean)

**Decision:** V2.0 ships with **8 EvalConfigTypes** in the `V2EvalType` enum and `V2EvalConfigProperties` union (6 original + `step_count_check` added by Batch J — see J.38 — + `code_eval` promoted per B.12). The catalog deliberately ships small — additional types are post-V2.0 additions to the same union (extensibility is open per A2.1 + Batch E #36 plugin contract).

**V2.0 must-ship (the launch surface):**

| Type | What it scores | Properties class |
|---|---|---|
| `llm_judge` | Subjective quality, factual accuracy, criteria pass/fail (with `g_eval_mode` toggle per A2.2) | `LlmJudgeProperties` |
| `exact_match` | Enum/string equality vs `reference[key]` | `ExactMatchProperties` |
| `pattern_match` | Regex on output / trace / field-path | `PatternMatchProperties` |
| `set_check` | Set containment (subset / superset / intersection) vs reference | `SetCheckProperties` |
| `tool_call_check` | Tool trajectory: existence / ordering / forbidden + per-arg matching (properties expanded in J.37) | `ToolCallCheckProperties` |
| `contains` | Substring presence/absence | `ContainsProperties` |
| `step_count_check` | Agent efficiency: count of tool calls / model responses / turns vs bounds (added in J.38) | `StepCountCheckProperties` |
| `code_eval` | User-authored Python scorer — long-tail expressiveness escape hatch (per B.12; gate resolved by B.13) | `CodeEvalProperties` |

(That's 8 — 6 original + `step_count_check` from Batch J + `code_eval` promoted from conditional per B.12.)

**Post-V2 (not in the V2.0 launch enum; added later as plugins or built-ins):**

| Type | Why deferred |
|---|---|
| `composite` | Used in kintsugi but Steve flagged "not important." Defer until real demand. |
| `threshold` | Defer; numeric-score → pass/fail bridge isn't a V2.0 differentiator. |
| `json_schema` | Defer; library-backed, can land in V2.x without redesign. |
| `event_ordering` | Defer (Steve moved from conditional/should-ship to post-V2). |
| `embedding_similarity` | Could-ship-later; needs embedding model call, not blocking V2.0. |
| `dag_metric` | Could-ship-later; design exploration, not a V2.0 differentiator. |

**Out of scope for this V2 alignment project:**

- `multi_turn_synthetic` — designed by parallel multi-turn-synthetic project. Inclusion in V2.0 launch is a parallel-track decision, not locked here. EvalInput's `MultiTurnSyntheticEvalInputData` shape (per A1.1) accommodates it whenever the parallel project lands.

**Implications of the lean catalog:**

- V2.0 launch differentiates on (a) the EvalInput data model + reference-data contract (Batch A1), (b) the typed-config / coexistence story (A2.1-A2.11), and (c) the enhanced `llm_judge` (per-criterion verdicts, trace condensation, reference templating — Stage 5 `design/21`). Not on a wide type catalog. *(The feedback pipeline was an originally-listed differentiator but was PUNTED out of evals V2 on 2026-06-03 — see Batch F.)*
- Stage 5 per-type design docs that get written for V2.0: `design/21_type_llm_judge.md`, `design/22_type_deterministic_basics.md` (covers exact/pattern/set/contains/tool_call/step_count together since they share the path-extraction infrastructure), and `design/27_type_code_eval.md` (in-scope per B.12 — `code_eval` is a planned V2 type). Other per-type docs (`design/23_type_composite.md`, `design/24_type_threshold_and_json_schema.md`, `design/25_type_event_ordering.md`) become post-V2 design docs or deferred entirely.
- Stage 6 Phase 1 ("must-ship EvalConfigTypes") catalog needs an update — currently lists `composite` and enhanced `llm_judge`'s should-ship items as Phase 1.  See PLAN.md update below.

**Unblocks:** Stage 5 per-type design scope is now bounded. Phase 0 schema (A2.1's `V2EvalType` enum) ships with exactly these 8 values plus the discriminator infrastructure for adding more. Batch G (builder UX) routes onto a known finite set of types.

**Plugin extensibility (Batch E #36):** The union is open-ended — third parties (or future V2.x built-ins) add new `V2EvalType` enum values and new properties classes to the discriminated union. The lean V2.0 catalog is the *launch* surface, not the *possible* surface.

**Agent-eval expansions — LOCKED in Batch J (2026-06-02):**
- **Decision 37** ([J.37](#j37-tool_call_check-properties-expansion)) — `tool_call_check.properties` expanded (no catalog change) to cover ordering, forbidden-tool, and per-arg matching modes. Parity with Promptfoo's 3 trajectory assertion types in one properties schema.
- **Decision 38** ([J.38](#j38-step_count_check--new-evalconfigtype)) — `step_count_check` added as a V2.0 catalog entry (reflected in the table above). Closes the agent-eval efficiency category.

Both motivated by the 2026-05-22 competitive scorecard: agent-eval coverage was 1 of 4 categories vs Promptfoo's 4/4. The two together bring parity. See Batch J section below for locked shapes.

---

## Batch F — Feedback pipeline + triage — PUNTED to a future standalone project (2026-06-03)

**The entire feedback pipeline is out of scope for evals V2.** Decided 2026-06-03 with Steve. This includes all remaining decisions (22 unified score model, 23 triage data model, 24 clustering, 25 corrected-output promotion, 25c V1/V2 routing, 26 self-improving judges) **AND the two early-locked decisions F.1 and F.2 below, which are hereby un-locked / deferred.**

**Why:** The only evals-V2 footprint of the feedback pipeline is additive data-model change — a few fields on the `Feedback` model and a `feedback → EvalInput` conversion helper (F.1/F.2). That pre-commits data shape for a project that has not been planned. Per A0.1 everything here is additive, so it costs nothing to add when the **Feedback Pipeline** project is actually designed. Nothing in V2.0 (no eval type, no runner path, no in-scope dataset-creation flow) reads feedback data. EvalInputs in scope come from synthetic generation (K.3), where the feedback-derivation fields would be null/unused anyway.

**Consequences (applied):**
- `EvalInput` ships in evals V2 **without** `source_task_run_id`; the field is added later, additively, by the Feedback Pipeline project. F.1 removed from `design/10_data_model.md` alignment_refs.
- K.3's "`source_task_run_id` is None" clause is dropped — the field simply doesn't exist in the V2 EvalInput; V2 dataset generation sets nothing.
- A0.5 ("Feedback closes the loop") stays as a stated north-star direction but its **implementation is deferred** to the future project — it is not a V2.0 deliverable.
- `design/60_feedback_and_triage.md` is out of scope for this project (see design_dispatch.md).

The original early-lock entries are preserved below for the future project to pick up, marked DEFERRED.

### F.1. Source linkage on derived EvalInputs — DEFERRED (un-locked 2026-06-03)

**Decision:** When a feedback item converts into an EvalInput (via the "promote as reference" or "assign to eval" conversion path), the new EvalInput records its source: `source_task_run_id: str | None`. Null-safe — the field is optional and persists as None if the source is unknown or later deleted.

**Rationale:** Traceability — "this eval case came from a real production bug" is high-value provenance for triage and audit. The null-safety preserves robustness if the source TaskRun is later deleted (eval continues to work; the link just resolves to None).

**Unblocks:** Triage workspace UX can surface "where did this case come from?" without ambiguity. Feedback pipeline (Batch F) has a clean linking mechanism.

---

### F.2. Snapshot semantics for derived EvalInputs — DEFERRED (un-locked 2026-06-03)

**Decision:** When deriving an EvalInput from a source TaskRun, the source data is **snapshotted** (copied) into the new EvalInput at derivation time. The EvalInput is self-contained and does not live-read from the source TaskRun on subsequent eval runs.

**Specifics:**
- TaskRun input → copied into `user_message: UserMessage` (or other input field per variant) at derivation time.
- Corrected output (if present) → stored in `reference` as appropriate key (e.g. `reference["corrected_output"]`).
- `source_task_run_id` (per F.1) records the origin, but is NOT used for re-fetching.

**Rationale:** Reproducibility. If a user later edits the original TaskRun (or deletes it), the eval still runs identically. Eval datasets must be stable — drift from upstream sources would invalidate historical eval comparisons. Consistent with kintsugi's case-as-self-contained-record model.

**Unblocks:** Eval re-runs are reproducible across time. Eval dataset versioning (Batch E open #33) doesn't need to also version source TaskRuns.

---

## Batch C — Cardinality + score attribution (in progress)

### C.9. Eval ↔ EvalConfig cardinality — semantically 1:1 (operative config via `current_config_id`); 1:N on disk for calibration candidates

**Decision:** V2 preserves V1's cardinality model unchanged. **Semantic model is 1:1** — one Eval has one operative EvalConfig (the one pointed to by `current_config_id`). On disk, an Eval may have N child EvalConfigs — the non-current ones are **calibration candidates** (different prompts, models, types attempting to produce the same scores), not concurrent scoring contributors.

**What this is:**
- **Eval = one scoring goal** with N dimensions declared by `output_scores: list[EvalOutputScore]` (e.g., `accuracy`, `tone`, `safety`).
- **`current_config_id` = the candidate validated against the golden subset (`eval_configs_filter_id`) and promoted to "in production."** Normal eval runs (`task_run_eval` mode) invoke ONLY this config.
- **Non-current EvalConfigs = calibration candidates** — possibly bad, possibly being tested, possibly historical. They exist on disk so the `eval_config_eval` calibration mode can score them against the golden subset to drive promotion decisions.
- **Multi-signal per case = `output_scores` within one config**, not multi-config. If you want a fundamentally different scoring approach, create a different Eval.

**What this is NOT:**
- Not "N active configs all running concurrently producing different signals per case" (the redundant-attempts trap — every candidate is trying to produce the same scores; running all of them on every input is wasteful).
- Not a refactor toward a 1:N "active list" (option (b) from `_synthesis.md:117-119` is rejected).

**Candidate type constraint — Option (b): different EvalConfigTypes allowed under one Eval if outputs match.** Candidates under one Eval may be different `V2EvalType`s (e.g., a `pattern_match` candidate alongside an `llm_judge` candidate) **so long as the produced scores conform to `Eval.output_scores` shape**. This preserves alignment calibration math — candidates remain directly comparable on the same headline scores.

**Validation — result-time only (V1 mechanism preserved):** `EvalRun.validate_scores` (`eval.py:181-237`) already validates at EvalRun save time that scores keys + value ranges match the grandparent `Eval.output_scores`. V2 inherits this unchanged — same check applies to V2 EvalConfigs. A misconfigured config (wrong type, wrong shape) fails on its first run. No new bind-time validator — keep it simple.

**Why preserve cardinality unchanged:**
- The V1 model is correct for the actual workflow: alignment-via-calibration. You build several judge candidates, test them against humans on a golden subset, promote the one that aligns best. The candidates aren't more evals — they're attempts at the same eval.
- A 1:N concurrent refactor would conflate "scoring goal" with "scoring approach" and create wasteful redundant scoring on production runs.
- Alternative scoring goals are modeled as separate Evals (cheaper than a complex multi-config-per-eval model).

**Consequences for already-locked decisions** (all consistent — no re-opens):
- A1.3 (multi-config-per-input reference data, flat): works for calibration — multiple candidates read shared EvalInput.reference, each picking keys it consumes.
- A2.3 (per-config data extraction): each candidate (current or not) declares its data needs in properties.
- A2.6 (`eval_input_id` orthogonal source field on EvalRun): unchanged.
- A2.10 / A2.11 (adapter dispatch): unchanged.

**Application of A0 principles:**
- [A0.1](#a01-backwards-compatibility--v2-reads-v1-v2-never-migrates-v1): V1 Evals continue using `current_config_id` unchanged. V2 Evals do too. No schema change.
- [A0.2](#a02-many-small-evals--and-a-builder-that-right-sizes-datasets-to-input): "many small evals" reinforced — multi-approach = multi-Eval, not multi-config-under-one-Eval.

**Unblocks:**
- Decision 10 (config-to-score assignment) — resolved by inheritance: each EvalConfig produces all of `Eval.output_scores` (V1 model preserved). No new mapping mechanism needed.
- Stage 5 `design/45_runner_architecture.md` — runner dispatches `task_run_eval` mode to `current_config_id` only; `eval_config_eval` mode runs all candidates.

**Plan deltas:**
- `alignment_plan.md` decision 9: mark locked here.
- `alignment_plan.md` decision 10: mark resolved-by-inheritance.

**Linked opens** (resolved or moved below):
- C.5 (`SyntheticUserInfo` shape) — resolved as contract-only lock in C.5 below.
- Eval skips on missing reference data — resolved in C.runner.1 below.
- `EvalRun.validate_output_fields` V2 bypass — resolved in C.runner.2 below.

---

### C.5. `SyntheticUserInfo` — lock contract, defer field list to parallel project

**Decision:** Lock the **shape contract only**:
- `synthetic_user_info` is a typed Pydantic model on `MultiTurnSyntheticEvalInputData` (per A1.1).
- The model is **versioned** (carries an explicit `version` field or equivalent discriminator) so the parallel multi-turn project can evolve the field set without breaking V2 EvalInputs already on disk.
- The actual field list (`persona / goal / behavior / max_turns` vs kintsugi's freeform `follow_up_policy: str` vs some merger) is **owned by the parallel multi-turn-synthetic project**, not Stage 3.

**Out of scope for V2 Evals alignment:** field-level shape, defaults, validation rules. Those land when the parallel project locks its own design.

**Why this is enough for now:** A1.1 already commits the typed-model decision and the `MultiTurnSyntheticEvalInputData` host. Field-level details don't gate any other Stage 3 batch — every Batch C/D/E/F decision works whichever way the parallel project goes. The async handoff is cleaner than blocking on cross-project alignment.

**Application of A0:**
- [A0.6](#a06-doesnt-exist-today-is-design-space-not-a-gap-to-patch) — let the parallel project design the field set fresh, not as a delta against V1 (which has nothing) or kintsugi (which is prototype quality per PROJECT.md).

**Unblocks:**
- Batch C closure on cross-project coordination.
- Parallel multi-turn project can ship its own field design without Stage 3 sign-off.
- Stage 5 `design/26_type_multi_turn_synthetic.md` lands when the parallel project does.

**Linked open** (post-handoff): the parallel project's field-list decision. Tracked in their project, not here.

---

### C.runner.1. Missing reference data — skip + report

**Decision:** When an EvalInput is missing reference keys that a bound EvalConfig requires:
- **Runner skips that (input × config) combination.**
- Records the skip on a partial EvalRun (resolved by E.18) using the two-field model: `skipped_reason="missing_reference_key"` (a `SkippedReason` value) + `skipped_detail="<key_name>"`. (The earlier colon-suffix string `"missing_reference_key:<key>"` was superseded by the `skipped_detail` companion field per E.18 / design_phase_calls.md C1.)
- Contributes to `n_excluded` in aggregate metric provenance (per upcoming Batch E #18 — MetricValue provenance fields).
- Does NOT hard-fail the whole eval run. Other (input × config) combinations proceed normally.

**Why skip + report (not hard-fail, not skip + score partial):**
- **Best-effort partial eval is more useful than all-or-nothing.** A single missing key on one EvalInput shouldn't take down a 200-case eval.
- **Skip + score partial** (scoring with whatever data is present) would silently corrupt scores — if a judge expects `judge_criteria` and gets None, it shouldn't try to bluff a score. Skipping is honest.
- **Hard-fail** punishes the user for one bad data row.

**Reference contract reminder:** Per A1.2, each EvalConfigType declares the reference keys it consumes. The runner checks this contract at the start of each (input × config) job. Missing keys = skip; mismatched value types = skip (with reason).

**UX implication:** Reports surface skip counts and reasons. "12 of 200 inputs skipped because `judge_criteria` was missing" is actionable feedback to fix the dataset.

**Unblocks:**
- Stage 5 `design/45_runner_architecture.md` — runner contract on missing reference data is locked.
- Batch E #18 (MetricValue provenance) — `n_excluded` semantics now have a concrete source.

---

### C.runner.2. `EvalRun.validate_output_fields` — extend with `config_type` check (V2 bypass)

**Decision:** Extend the existing `EvalRun.validate_output_fields` validator at `eval.py:146-166` with a `config_type` check. When the grandparent `EvalConfig.config_type == "v2"`, skip the legacy field-presence gate. V1 EvalConfigs continue using the existing validator path unchanged.

**Why:** Per A2.3, V2 EvalConfigs declare their data needs in their own properties; the Eval-level `evaluation_data_type` is `None` for V2 Evals. The legacy validator reads `evaluation_data_type` from the grandparent Eval to gate `task_run_trace` / `reference_answer` presence — that gate is meaningless for V2 (the data contract has moved to per-config properties).

**Implementation sketch:**

```python
@model_validator(mode="after")
def validate_output_fields(self) -> Self:
    eval_config = self.parent_eval_config()  # existing parent EvalConfig lookup (grandparent Eval via .parent_eval())
    if eval_config and eval_config.config_type == EvalConfigType.v2:
        return self  # V2: per-config properties drive data contract; no Eval-level gate
    # ... existing V1 logic unchanged ...
    return self
```

**Why not a separate V2-specific validator:** The existing validator's V1 logic is correct for V1 EvalRuns. Adding a single-line bypass branch keeps both paths visible in one place and avoids a forked validator. Consistent with A0.1 (V2 is additive; V1 preserved).

**What V2 EvalRuns get instead:** No new validator at this layer — V2 data-contract validation lives in each EvalConfigType's properties (per A2.3) and is enforced at adapter bind time, not on EvalRun save. C.runner.1 (missing reference data) is the runtime contract for missing per-config data.

**Unblocks:**
- Phase 0 sub-task 3 (EvalRun model extension) — closes the linked open from A2.3.
- V2 EvalRuns load and save cleanly without bumping the legacy validator.

---

### C.runner.3. `EvalRunner.__init__` — extend constructor validation to accept EvalInput-sourced runs alongside TaskRun-sourced runs

**Decision:** Generalize the source-validation branch in `EvalRunner.__init__` (`eval_runner.py:64-78`) to accept EvalInput-sourced runs via `eval_input_filter_id` (per A2.5) alongside the existing TaskRun-sourced runs (`eval_set_filter_id` / `eval_configs_filter_id`). No new `eval_run_type` value; no init-path fork; no change to the `run_configs` invariant.

**The `run_configs` invariant stays unchanged:** `run_configs present iff eval_run_type == "task_run_eval"` — true for both V1 and V2. V2 changes nothing about run-mode semantics.

**Coverage matrix (V1 and V2 both work over either run mode):**

| Source | Run mode | `run_configs` | Data flow |
|---|---|---|---|
| TaskRun (V1, `eval_set_filter_id`) | `task_run_eval` | required | Existing — run task fresh on TaskRun input, judge |
| TaskRun (V1, `eval_configs_filter_id`) | `eval_config_eval` | not used | Existing — judge against stored TaskRun output |
| EvalInput (V2, `eval_input_filter_id`) | `task_run_eval` | required | NEW — runner reads `EvalInput.user_message`, runs via run_configs, judges output |
| EvalInput (V2, `eval_input_filter_id`) | `eval_config_eval` | not used | NEW — runner reads stored output (per Batch B2), judges only |

**Implementation:** Single new branch in the constructor:
- If `eval.eval_input_filter_id` is set: validate against EvalInput dataset path (loads EvalInput collection, checks all referenced configs share the parent Eval, etc.).
- Else: fall through to existing V1 source-validation (TaskRun dataset path).

The `run_configs iff task_run_eval` check is applied identically in both branches — it's mode-driven, not source-driven.

**Why not a new `eval_run_type` value:** Run mode and input source are orthogonal (the matrix above proves it). Adding a new enum value would conflate them and re-introduce the same conflation A2.6 cleaned up at the EvalRun level. Keep them orthogonal at the runner level too.

**Why not a forked init path:** Most of the existing constructor (skill preloading, parent-Eval consistency check, etc.) applies identically to both source types. A fork would duplicate that logic. The single-branch extension keeps both paths visible in one place — consistent with A0.1 (V2 is additive).

**Application of A0:**
- [A0.1](#a01-backwards-compatibility--v2-reads-v1-v2-never-migrates-v1) — V1 source-validation logic untouched. V2 branch is additive.

**Unblocks:**
- Phase 0 sub-task 7 (Runner extension) — closes the linked open.
- Stage 5 `design/45_runner_architecture.md` — runner constructor contract is locked.

---

### C.11b. V2 adapter registry — two-level dispatch

**Decision:** V2 uses two-level adapter dispatch. Top level: `eval_adapter_from_type` (signature per [A2.11](#a211-adapter-registry-signature-change--evalconfigtype--evalconfig)) branches on `EvalConfig.config_type`. If `v2`: dispatch to a V2 sub-registry keyed on `properties.type` (the inner discriminator from [A2.1](#a21-evalconfig-v2-shape-coexistence-with-v1)). Otherwise: existing legacy match on `EvalConfigType.g_eval` / `llm_as_judge` → `GEval`, unchanged.

**Rationale:** [A0.1](#a01-backwards-compatibility--v2-reads-v1-v2-never-migrates-v1) (V1 reads preserved) plus A2.11 (registry signature accepts full `EvalConfig`) make this the only consistent path. A unified registry would require either rewriting V1 dispatch or generalizing the `EvalConfigType` enum — both violate A0.1 for no gain. Implementation detail lives in A2.11 + `design/20_eval_config_types_overview.md` + `design/45_runner_architecture.md`.

**Unblocks:** Stage 5 `design/20_eval_config_types_overview.md` adapter-contract section. Phase 1 V2 adapter registration.

---

### C.11c. V2 adapter base class — generic `BaseEval` (no `BaseEvalV2` fork)

**Decision:** V2 adapters subclass the existing `BaseEval`. No separate `BaseEvalV2` class. Legacy-specific behavior (root-level `model_name` / `model_provider` access) is reached via the helper module introduced in [A2.10](#a210-model_and_provider-helper-extraction-baseeval-stays-generic); V2 LLM adapters read model fields from their own properties (per [A2.10](#a210-model_and_provider-helper-extraction-baseeval-stays-generic)); V2 non-LLM adapters inherit `BaseEval` cleanly without touching model fields.

**Rationale:** Forking the base class would couple V1/V2 lifetimes (every base-class change has to be made twice) and re-introduce the V1↔V2 coupling that A2.10's helper-extraction explicitly avoids. Implementation detail lives in A2.10 + `design/20_eval_config_types_overview.md`.

**Unblocks:** Per-type V2 adapter design (`design/21_type_llm_judge.md`, `design/22_type_deterministic_basics.md`, `design/27_type_code_eval.md`) — all assume a single `BaseEval` parent. Batch H decision 32a (legacy/V2 code reuse) treats the helper module as the seam.

---

## Batch D — Templates + extraction (reframed from "Filter pipeline")

**Source of truth:** `design/40_template_and_extraction.md` (drafted in this batch). This section is a short pointer + the locked principles. Open decisions are tracked in the design doc's `## Opens` section, not here.

### D.1. Reframe: filter pipeline → templates + extraction

**Decision:** Batch D's scope reframed during Group A from "filter pipeline + signal extractor abstraction" to **"templates + extraction primitive."** The original "filter as field on EvalConfig" framing was over-engineered. The actual need is:
1. A shared extraction primitive (`FilterSpec`) used by every type that needs to pull data out of an EvalInput/TaskRun.
2. A user-authored Jinja2 prompt template surface for `llm_judge` (V1's hardcoded f-string templates are a major competitive gap — `research_judge_prompts/_synthesis.md`).
3. No new chat formatter or prompt-builder infrastructure inside V2 evals — use Kiln tasks natively.

**Application:**
- Replaces the "filter-as-first-class-EvalConfig-field" framing.
- Subsumes decisions 15 and 16 from `alignment_plan.md` (those become resolved-by-design).
- Subsumes the V1-template-hardcoded competitive gap.
- Replaces `design/40_filtering_pipeline.md` (planned) with `design/40_template_and_extraction.md` (drafted).

### D.2. Templating + extraction reframed to GENERAL Kiln capability (Round 2, 2026-05-26)

**Decision:** Templating is NOT eval-owned. It's a general Kiln task capability via `input_transform` on `KilnAgentRunConfigProperties`. Evals V2 are the first consumer. `FilterSpec` is eliminated; jq is dropped from the eval path; one extraction mechanism (Jinja2 expressions via `extract()` helper) serves all consumers.

**Locks:**
- General infrastructure designed in `design/06_prereq_input_transform.md` (separate Kiln core prereq, see PLAN.md Phase 0 Prerequisite #3).
- V2 ships one concrete transform type: `JinjaInputTransform` (Jinja2 template that projects structured task input to model-facing string).
- Public API exported from `libs/core`: `render_input_transform`, `extract`, `compile_template_or_raise`, `compile_expression_or_raise`.
- Three reserved top-level template variables for eval consumption: `final_message`, `trace`, `reference_data` (plus `task_input`). No `data.` namespace wrapper.

**Application:**
- `exact_match`, `pattern_match`, `contains`, `set_check` — each has `value_expression: str | None = None` (Jinja2 expression evaluated via `extract()`).
- `llm_judge` — has `prompt_template: str` (REQUIRED, Jinja2 template) + `required_var: list[str]` (Jinja2 expressions pre-checked for non-null) + optional `system_prompt: str` + optional `thinking_instruction: str` + `g_eval: bool` (renamed from `g_eval_mode`).
- `tool_call_check` — typed exception, unchanged.
- `code_eval` — gets raw sources via helper lib (Phase 5), unchanged.

**Supersedes:** The Round 1 Batch D design (eval-owned `FilterSpec` + Jinja2 + per-type extraction). Old approach saved in git history.

### D.3. Eval consumer design

**Decision:** V2 evals run as Kiln tasks (per V1 `GEvalTask` pattern). Eval runner assembles a synthetic JSON input (`EvalTaskInput { final_message, trace, reference_data, task_input }`) per case. For `llm_judge`: constructs an eval task RunConfig with `JinjaInputTransform(template=prompt_template)`, pre-checks `required_var` expressions via `extract()`, skips with structured `skipped_reason` on null/Undefined. For simple-check types: calls `extract()` directly, compares result to `expected_value` / `reference_data[reference_key]`.

**No `template_vars` field on `LlmJudgeProperties`.** Templates access top-level synthetic-input fields directly (`{{ final_message.summary }}`). DRYing via Jinja2's built-in `{% set %}`.

**Save-time validation:** EvalConfig save runs `compile_template_or_raise(prompt_template)` and `compile_expression_or_raise(...)` for each `required_var` / `value_expression`. Invalid Jinja2 → save rejected. PLUS: useless-template rejection (at least one referenced var must come from `final_message`, `trace`, or `task_input` — not just `reference_data`).

**Application:** Full design in `design/40_template_and_extraction.md`.

### D.4. Use Kiln tasks natively

**Decision:** V2 evals are Kiln tasks. They inherit existing `BaseAdapter` → `litellm_adapter` → `chat_formatter` infrastructure. No new formatters built inside V2 evals.

**Consequences accepted:**
- User Jinja2 template gets wrapped in `<user_input>...</user_input>` by `TwoMessageCotFormatter` for non-reasoning models. Fine.
- Default `"Think step by step, explaining your reasoning."` appends after user template via inherited `thinking_instruction` fallback. Fine (`prompt_builders.py:294-305`).
- Two-turn for non-reasoning, single-turn for reasoning — inherited V1 behavior.
- Structured output mode selection inherited from `default_structured_output_mode_for_model_provider()`.
- `g_eval_mode=True` keeps the V1 function_calling disallow (logprobs depend on json_schema mode).

**Open as part of D.4 — system_prompt None handling (conditional resolution):** how V2 handles `system_prompt: None` depends on whether Kiln core makes system messages optional before V2 llm_judge implementation. **Rule:** if core change lands first → `None` means no system message emitted (matches 7/10 competitor majority). If core change doesn't land → V2 builder writes a default (`"You are an evaluator."`) **into the EvalConfig's `system_prompt` field at creation time** (not applied at runtime — preserves consistency-over-time so future Kiln default changes don't silently mutate old eval behavior). **Verification step before V2 llm_judge implementation:** check the state of "make Kiln core system message optional" work. Details in `design/40_template_and_extraction.md` §7.1.

**Resolved as part of D.4 — thinking_instruction:** V2 llm_judge carries forward V1's pattern. Optional `thinking_instruction: str | None` on `LlmJudgeProperties`; if None at creation, V2 builder writes Kiln's current default string (`"Think step by step, explaining your reasoning."`) into the EvalConfig datamodel for consistency-over-time. Details in `design/40_template_and_extraction.md` §7.2.

### D.5. V1 backwards compatibility — absolute

**Decision:** V1 EvalConfigs (`config_type: "g_eval"` / `"llm_as_judge"`) continue to use the existing `GEval` adapter, the existing three hardcoded `generate_*_run_description` f-strings, the existing `EvalDataType` enum at the Eval level. **Zero V1 behavior changes**, ever. Per A0.1.

**Scope of "zero V1 behavior changes" (clarified 2026-06-03):** This covers the **read + execution** of existing V1 records on disk — how an already-saved V1 EvalConfig parses, dispatches, and runs. It does NOT mean "creation endpoints must keep emitting V1 shape": K.3 intentionally changes the manual/Copilot creation paths to emit V2-shaped EvalConfigs going forward (no new V1 records created). Existing V1 records are never rewritten, re-parsed differently, or run differently. The creation-path change is consistent with A0.1 (which governs migration of on-disk data, not what new data the app authors).

**Application:** V2 path is fully additive. Code sharing between V1 and V2 is via refactored helpers (Batch H 32a), not by mutating V1 paths.

---

## Batch A2 (continued)

### A2.6. EvalRun coexistence — keep `eval_config_eval` bool, add `eval_input_id` as orthogonal source field

**Decision:** `EvalRun.eval_config_eval: bool` stays as-is, single purpose — indicates **what's being evaluated** (run config vs eval config). Input source is modeled as a separate, orthogonal dimension via two fields: `dataset_id` (V1 TaskRun source) XOR `eval_input_id` (V2 EvalInput source). A new validator enforces exactly one of the two is set.

**Schema:**

```python
class EvalRun(KilnParentedModel):
    # ... existing fields unchanged ...
    eval_config_eval: bool = False              # UNCHANGED — what's being evaluated
    dataset_id: ID_TYPE | None                  # CHANGED to optional — V1 TaskRun source
    eval_input_id: ID_TYPE | None = None        # NEW — V2 EvalInput source

    @model_validator(mode="after")
    def validate_input_source(self):
        if (self.dataset_id is None) == (self.eval_input_id is None):
            raise ValueError("Exactly one of dataset_id or eval_input_id must be set")
        return self
```

**Rationale:** "What we're evaluating" and "where the input data comes from" are orthogonal concepts. The earlier proposal (a `run_type` Literal of `["task_run_eval", "eval_config_eval", "eval_input_eval"]`) conflated them. Keeping `eval_config_eval` as a single-purpose bool and modeling input source as separate fields is cleaner: V1 evals continue using `dataset_id`; V2 evals using EvalInputs populate `eval_input_id`; either can be paired with `eval_config_eval=True` or `False`.

**Unblocks:** EvalRun coexistence path for Phase 0. Runner dispatch reads `dataset_id` vs `eval_input_id` to pick the source; reads `eval_config_eval` to pick the run mode. Both dimensions handled independently.

**Linked open** (resolves in **Batch B2**): When V2 runs `eval_config_eval=True` with an `eval_input_id` source, the EvalInput needs to carry an output to be evaluated. The shape of that output storage is its own design question — see `batch_b2_golden_dataset_outputs.md`.

---

### A2.7. EvalRun V2 reference data — new additive `reference_data` field

**Decision:** V2 EvalRuns store reference data in a new optional field `reference_data: dict[str, JsonValue] | None`. The legacy `reference_answer: str | None` field is untouched (V1 EvalRuns continue to use it). The existing `validate_reference_answer` validator stays exactly as-is — it gates only `reference_answer`, never `reference_data`.

**Schema:**

```python
class EvalRun(KilnParentedModel):
    # ... existing fields unchanged ...
    reference_answer: str | None = None         # UNCHANGED — V1 snapshot from TaskRun.output.output
    reference_data: dict[str, JsonValue] | None = None  # NEW — V2 reference sourced from EvalInput.reference
```

**Rationale:** Adding a separate field for V2 reference data preserves V1 semantics entirely (`reference_answer` validator unchanged, V1 runners read it as before) while letting V2 carry structured per-key reference data sourced from `EvalInput.reference`. The alternatives (extending the legacy validator, reusing `reference_answer` with new semantics) would couple V1 and V2 read paths in the same field.

**Unblocks:** V2 runner can populate `reference_data` from EvalInput.reference at run time; V2 adapters read from there. Legacy adapters keep reading `reference_answer` unchanged.

---

### A2.8. EvalConfig.properties parsing — explicit `mode="before"` routing validator

**Decision:** Use an explicit Pydantic `model_validator(mode="before")` on `EvalConfig` that reads `config_type` and routes parsing of `properties` to either the V2 discriminated union or the legacy `dict[str, Any]`. Do NOT rely on Pydantic's implicit union fallback ordering.

**Schema sketch:**

```python
@model_validator(mode="before")
@classmethod
def dispatch_properties_parsing(cls, data: dict, info: ValidationInfo) -> dict:
    if not isinstance(data, dict):
        return data
    config_type = data.get("config_type", "g_eval")
    if config_type == "v2":
        # let V2EvalConfigProperties discriminated union handle parsing
        pass
    else:
        # legacy — keep properties as raw dict
        pass
    return data
```

**Rationale:** Implicit Pydantic union fallback (`V2EvalConfigProperties | dict[str, Any] | None`) works in practice but relies on parse-order semantics. Risk: a legacy V1 dict that happens to contain a `type` key matching a V2 type could mis-parse silently. The explicit validator removes the ambiguity — `config_type` (already authoritative) drives parsing.

**Unblocks:** Robust V1 file loading. Future V2 type additions don't risk collision with legacy dict keys.

---

### A2.9. `eval_set_filter_id` becomes optional with mutual-exclusivity validator

**Decision:** In V2's class definition, change `Eval.eval_set_filter_id` from required (`DatasetFilterId`) to optional (`DatasetFilterId | None = None`). Add a model validator enforcing exactly one of `{eval_set_filter_id, eval_input_filter_id}` is set on V2 Evals.

**Schema:**

```python
class Eval(KilnParentedModel):
    # ... existing fields ...
    eval_set_filter_id: DatasetFilterId | None = Field(default=None, ...)  # CHANGED — optional
    eval_input_filter_id: EvalInputFilterId | None = Field(default=None, ...)  # NEW per A2.5

    @model_validator(mode="after")
    def validate_filter_fields(self):
        if (self.eval_set_filter_id is None) == (self.eval_input_filter_id is None):
            raise ValueError(
                "Exactly one of eval_set_filter_id or eval_input_filter_id must be set"
            )
        return self
```

**V1-vs-V2 framing:** V1 clients are compiled against the V1 class definition where `eval_set_filter_id` is required — V1's runtime behavior is unchanged. V2's class definition is more permissive but adds the mutual-exclusivity validator to enforce a V2 contract. The two contracts coexist via separate compiled class definitions.

**Rationale:** V2 Evals using EvalInput datasets (per A2.5) don't have a TaskRun filter and shouldn't be required to set one. Making the field optional in V2's definition is safe (V1 has its own definition); the validator prevents accidental misconfiguration.

**Unblocks:** V2 EvalInput-backed Evals can be created without legacy filter requirements. Phase 0 can ship the Eval extension cleanly.

---

### A2.10. `model_and_provider` helper extraction; `BaseEval` stays generic

**Decision:** Extract `BaseEval.model_and_provider()` (currently at `base_eval.py:40-54`) into a separate helper module (e.g. `kiln_ai/adapters/eval/legacy_model_fields.py`). Legacy `GEval` calls the helper to read root-level `model_name`/`model_provider`. V2 adapters do NOT use the helper — V2 `llm_judge` reads `model_name`/`model_provider` directly from its own properties (`LlmJudgeProperties`); V2 non-LLM adapters never touch model fields.

**Architecture:**
- `BaseEval` — true base class, no LLM coupling. (Verified `BaseEval.__init__` at `base_eval.py:21-38` already does NOT read `model_name`/`model_provider` — only `model_and_provider()` does.)
- Legacy `GEval` — calls helper to read root fields.
- V2 `llm_judge` — reads `self.eval_config.properties.model_name` / `.model_provider` directly (no helper).
- V2 non-LLM types (`exact_match`, `pattern_match`, etc.) — inherit `BaseEval` cleanly, never touch model fields.

**Rationale:** Decouples LLM-specific field access from the base class. Avoids the alternatives (a separate `BaseEvalV2` class, or guarded reads in `BaseEval`) — both of which would either fork the base or couple V1/V2 semantics. The helper-extraction approach keeps `BaseEval` minimal and gives each adapter family the right access pattern.

**Unblocks:** Clean V2 adapter implementations. Batch H decision 32a (legacy/V2 code sharing) can build on the helper as the seam.

---

### A2.11. Adapter registry signature change — `EvalConfigType` → `EvalConfig`

**Decision:** Change the signature of `eval_adapter_from_type` (in `registry.py`) from taking `EvalConfigType` (the enum) to taking the full `EvalConfig` object. Internal API; one call site to update (`eval_runner.py:204`).

**Rationale:** V2 dispatch needs to read `properties.type` to pick the right V2 adapter — only the full EvalConfig provides this. Taking the enum alone is insufficient.

```python
# registry.py (new signature)
def eval_adapter_from_type(eval_config: EvalConfig) -> type[BaseEval]:
    if eval_config.config_type == EvalConfigType.v2:
        return v2_eval_adapter_from_properties_type(eval_config.properties)
    # legacy dispatch
    match eval_config.config_type:
        case EvalConfigType.g_eval:
            return GEval
        case EvalConfigType.llm_as_judge:
            return GEval
        case _:
            raise_exhaustive_enum_error(eval_config.config_type)
```

**Unblocks:** Two-level adapter dispatch (per Batch C 11b) can be implemented cleanly.

---

### A2.5. DatasetFilter coexistence — separate filter types for V1 and V2 datasets

**Decision:** `DatasetFilter` (existing, typed to `TaskRun`) stays TaskRun-only forever — no generalization, no union. A new `EvalInputFilter` protocol/callable is introduced for V2 evals using EvalInput datasets. `Eval` gains a new `eval_input_filter_id: str | None` field; V1 filter fields (`eval_set_filter_id`, `eval_configs_filter_id`) remain TaskRun-typed.

**Coexistence rules:**
- V1 evals: V1 filter fields populated, new `eval_input_filter_id` is None. Runner uses TaskRun path.
- V2 evals using EvalInput datasets: V1 filter fields are None, new `eval_input_filter_id` is populated. Runner uses EvalInput path.
- Runner dispatches by which field is set on the Eval.

**Rationale:** Application of [A0.1](#a01-backwards-compatibility--v2-is-additive-v1-is-preserved). Generalizing `DatasetFilter` to accept `EvalInput | TaskRun` would risk subtle breakage of every existing filter callable (they're typed `(TaskRun) -> bool`). Separate types keep V1 filter logic untouched and let V2 filter logic be designed cleanly for EvalInput's richer shape.

**Unblocks:** V2 runner architecture (Batch C). EvalInput-backed evals can be implemented without touching `DatasetFilter` semantics. Filter UI for V2 can be designed against `EvalInput` fields directly (tags, reference keys, etc.).

---

## Batch E — Cross-cutting model decisions (in progress)

### E.17. Score provenance / audit trail — no V2 changes required

**Decision:** V2.0 introduces no new score-provenance fields or entities. The existing Kiln `parent_of` chain (`EvalRun → EvalConfig → Eval → Task`, all `KilnParentedModel`) already records, for every score: which immutable EvalConfig produced it (carrying `config_type`, `model_name`, `model_provider`, `properties`), which Eval governs the output-scores spec, and `KilnBaseModel.created_at` for when. EvalConfigs are write-once by Kiln convention — old EvalRuns continue to point at the exact config that produced them. The question "where did this score come from?" already has a complete answer.

**What this rules out for V2.0:**
- Inspect-style inline `Score.history: list[ScoreEdit]` (audit trail for post-hoc edits).
- Separate `ScoreAudit` child entity.
- New provenance fields on EvalRun (`eval_config_hash`, `scorer_version`, `scoring_metadata`).

**Why not:** None of these solve a problem V2.0 has. Post-hoc score editing is not a V2.0 surface — V2.0 has no "correct this score" UX. Adding a `history` field that ships empty is schema weight for a feature that doesn't exist.

**Future revisit trigger:** If/when the feedback pipeline (PLAN.md Phase 4) introduces a "correct this score" UX, revisit Inspect-style inline history on the score record. That's a Phase 4 / Batch F discussion, not Batch E.

**Application of A0:**
- [A0.6](#a06-doesnt-exist-today-is-design-space-not-a-gap-to-patch) — applied inversely: "exists today" cleanly, no design space needed.

**Unblocks:** `design/85_observability_and_audit.md` — score-level provenance section is a 1-paragraph "existing parent_of chain is sufficient" note; no new schema. The file's substantive content is decisions 18 (MetricValue provenance), 21 (statistical primitives, deferred), and any skip-record persistence shape from C.runner.1.

**Plan deltas:** None. PLAN.md Phase 0 sub-task list unchanged.

---

### E.18. Skip persistence + n_used/n_excluded surfacing — additive EvalRun field; no persisted aggregate

**Decision:** No persisted MetricValue / aggregate metric entity (would create a second source of truth — aggregation stays on-read in `eval_api.py`). To distinguish "permanently skipped" from "not run yet" or "ran transiently failed," V2 adds a new optional field `skipped_reason: str | None = None` on EvalRun, plus a companion `skipped_detail: str | None = None` carrying case-specific specifics (V2-additive per A0.1; V1 EvalRuns load with None). Skipped EvalRuns are a terminal state — counted toward `percent_complete`, excluded from score means. Transient failures are NOT persisted; they surface to UI ephemerally, and DB-level absence ("incomplete") remains the correct signal for retry-able / not-yet-run cases.

> **Stage-5 reconciliation (2026-06-05, per design_phase_calls.md C1):** `skipped_reason` is stored as a **tolerant `str`** (not a strict enum *type*) for back/forward-compat — an unknown value won't crash on load. `SkippedReason(str, Enum)` is the **producer convention** with six canonical values (below); consumers match against it but tolerate unknown strings. A companion `skipped_detail: str | None` carries the case-specific information (missing key name, failed expression, unavailable type) that the original colon-suffix string design (`"missing_reference_key:<key>"`) tried to encode. Authoritative schema: `design/85` (canonical), `design/10`, `design/45`.

**Schema (EvalRun additions):**

```python
class SkippedReason(str, Enum):
    # Producer convention (six canonical values, locked Stage 5 / C1). Stored as plain str on EvalRun.
    missing_reference_key = "missing_reference_key"
    extraction_failed = "extraction_failed"
    missing_trace = "missing_trace"
    incompatible_input_shape = "incompatible_input_shape"
    code_eval_not_trusted = "code_eval_not_trusted"
    type_not_available = "type_not_available"

class EvalRun(KilnParentedModel):
    # ... existing fields unchanged ...
    skipped_reason: str | None = None    # NEW — V2-additive; tolerant str, SkippedReason convention
    skipped_detail: str | None = None    # NEW — case-specific detail (key name, expression, type)
    # Validator: if skipped_reason is set, scores may be empty/None (skipped runs carry no scores).
```

**Existing required-field validators that a skipped EvalRun must bypass (implementation note, added 2026-06-03 from the Stage 3c consistency pass):** A terminal skipped EvalRun carries no scores and may carry no output, but two existing validators currently make those mandatory:
- `EvalRun.validate_scores` (`eval.py:181-237`) requires `scores` to be non-empty. Must be extended: when `skipped_reason is not None`, allow empty/None scores.
- `EvalRun.output: str` is a required field (and any output-presence validator). A run skipped *before* task execution has no output. **Stage-5 pick (2026-06-05):** `output` becomes `str | None = None` (None when skipped; design/45 `_persist_skipped_run` sets `output=None`), rather than a sentinel.

These are additive V2-aware relaxations (V1 EvalRuns never set `skipped_reason`, so their behavior is unchanged — consistent with A0.1). Detail: `design/45_runner_architecture.md` + `design/10_data_model.md` section 5.4.

**On-read aggregation rules (eval_api.py changes):**
- `n_used` = EvalRuns with all expected `score_keys` populated AND `skipped_reason is None`.
- `n_excluded` = EvalRuns with `skipped_reason is not None`.
- `percent_complete = (n_used + n_excluded) / dataset_size` (skipped runs count toward completion).
- Score means computed only over `n_used` EvalRuns.

**API surface additions:**
- `ScoreSummary` / `EvalResultSummary` response shapes gain `n_used: int` and `n_excluded: int` per `(run_config_id × score_key)`.
- No `n_pending` / `n_failed_retryable` counts — `1 - percent_complete` covers those.

**API/UI division of labor unchanged:** Aggregation function returns whatever it can compute plus completion metadata (`percent_complete`, `n_used`, `n_excluded`); UI gates display of incomplete-eval results. Today the UI hides means below some completion threshold — V2 preserves this. UI also surfaces a warning + tooltip when `n_excluded > 0` ("3 of 50 cases skipped — required reference data missing").

**What this rules out for V2.0:**
- Persisted `MetricValue` / `EvalRunSummary` aggregate entity (rejected — second source of truth).
- `failure_reason` field for transient failures (rejected — DB only persists terminal states; retry handles transient).
- *Pure* free-form `skipped_reason: str` with no convention (rejected — the `SkippedReason` enum gives stable categorization for rollups/UI copy). Note: the field is *stored* as a tolerant `str` per the Stage-5 reconciliation above, but producers set it to a `SkippedReason` value; case-specific text goes in `skipped_detail`, not in the reason.

**Resolves the C.runner.1 open** ("lightweight skip record OR partial EvalRun") in favor of **partial EvalRun with `skipped_reason` enum**. One entity, fewer file types, fewer aggregation queries.

**Resolved in Stage 5:**
- `SkippedReason` enum value list — **locked** to the six canonical values above (`design/45` section, `design/85` section 2.2).

**Punted past Stage 5 (implementation-time):**
- Exact UI copy + completion-threshold heuristic for hiding incomplete eval means.

**Application of A0:**
- [A0.1](#a01-backwards-compatibility--v2-reads-v1-v2-never-migrates-v1) — V1 EvalRuns load unchanged with `skipped_reason = None`; V1 aggregation paths see `n_excluded = 0` and behave identically.

**Unblocks:**
- `design/85_observability_and_audit.md` — primary detail (skip semantics, aggregation rules, API response shape).
- `design/10_data_model.md` — `skipped_reason` field on EvalRun.
- `design/45_runner_architecture.md` — `SkippedReason` enum seed values + runner skip-emission contract.
- PLAN.md Phase 0 sub-task 3 (EvalRun model extension) gains the new field.

**Plan deltas:**
- PLAN.md Phase 0 sub-task 3: add `skipped_reason: SkippedReason | None = None` to the EvalRun model extension list.
- PLAN.md Phase 1: aggregation API uplift (`n_used` / `n_excluded` in `ScoreSummary` + UI warning) — fits naturally alongside score provenance fields (no new fields needed there per E.17).

---

### E.19. Composite policy registry — deferred post-V2

**Decision:** Composite policy registry design is **deferred to post-V2** alongside the `composite` EvalConfigType (per A2.4 — composite was flagged "not important" at catalog scoping). No V2.0 schema hook, field, or placeholder needed — named composite policies (`tiered_60_40`, `blocking_only`, etc. from kintsugi) are consumed only by the composite type, which doesn't ship in V2.0. When composite lands as a V2.x type, its policy field lives inside `CompositeProperties` (per A2.1's extensible discriminated union). No advance reservation required from V2.0.

**V2.0 reservation check:** Confirmed nothing to reserve. `Eval.output_scores` (per A1) + per-config scoring (per C.9, V1-preserved cardinality) already give a future composite type everything it needs — N child configs scoring into the same `output_scores` shape, plus a composite-owned policy field for combining them.

**Unblocks:** `design/90_open_risks.md` lists composite (and its policy registry) as a deferred post-V2 type. No design file authoring needed for V2.0.

**Plan deltas:** None. PLAN.md Phase 7 already lists `composite` as post-V2.

---

### E.20. Blocking vs quality tier — deferred post-V2

**Decision:** Tier (`blocking | quality`) is **deferred to post-V2** alongside composite (E.19, A2.4). No `tier` field on `EvalOutputScore`, on `EvalInput.reference`, or anywhere else in V2.0. UI treats all output scores equally. When composite ships as a V2.x type, tier lives either on `EvalOutputScore` (per-score-key) or inside `CompositeProperties` (composite-local) — that placement decision lands with composite design, not now.

**What this rules out for V2.0:**
- A `tier: blocking | quality | None` field on `EvalOutputScore` for display-only purposes (rejected — same anti-pattern as E.17's empty `score_history`: schema weight for an absent feature; UI affordance without an aggregation policy is meaningless to users).
- Per-case tier inside `EvalInput.reference` (rejected — kintsugi-style per-case construct complicates A1.2's flat reference contract for zero V2.0 benefit).

**V2.0 display gap acknowledged:** Users can't visually distinguish "blocking" from "quality" failures in V2.0 dashboards. Acceptable trade — no current competitor surfaces tier as a display concept without an aggregation policy backing it; UX would confuse without semantics.

**Unblocks:** `design/90_open_risks.md` notes tier-as-display as a deferred-along-with-composite item.

**Plan deltas:** None.

---

### E.21. Statistical comparison primitives — deferred post-V2, on-read utilities only

**Decision:** Statistical comparison primitives (matched-case intersection, paired-difference analysis, Wilson CI, paired bootstrap CI, Wilcoxon signed-rank) are **deferred to post-V2** (consistent with PLAN.md Phase 7). When they land, they are pure on-read utility functions in a future module (e.g., `kiln_ai/eval/stats.py`) consumed at report/render time. **No persisted aggregates, no new schema, no V2.0 hook required** — per-case scores in existing EvalRuns are sufficient input.

**What kintsugi does** (`reports/kintsugi_gaps.md:48-53`): `comparator.py` + `stats.py` provide `matched_intersection()`, `matched_aggregate()`, `per_case_paired()`, `wilson_difference_ci()`, `paired_bootstrap_diff_ci()`, `wilcoxon_signed_rank_p()`. The renderer uses these to surface "is this difference between Config A and Config B real or noise?" with CIs and p-values alongside raw means.

**Why deferred:**
- V2.0 ships raw on-read aggregates only (means, percent_complete, `n_used`/`n_excluded` per E.18). Sufficient for the V2.0 launch surface.
- Kiln's "compute on-read, no second source of truth" principle (established in E.18) extends here naturally — comparison primitives compute on demand; datasets are small enough for on-the-fly stats.
- Zero schema impact. Deferral is cheap to revisit; no lock-in.

**Where they would live (post-V2):** Utility module consumed by the aggregation/comparison API layer. Not embedded in `eval_api.py`'s existing functions; called by them when comparison views are requested.

**V2.0 acknowledgement of the gap:** V2.0 dashboards display raw side-by-side means without CIs or significance. Acceptable trade for V2.0 — most competitors (Promptfoo, DeepEval, LangSmith, Braintrust) also lack built-in matched-case + statistical-significance UX. Adding it post-V2 is a meaningful differentiator opportunity, not a launch requirement.

**Unblocks:** `design/90_open_risks.md` notes statistical primitives as a deferred analytics enhancement.

**Plan deltas:** None. PLAN.md Phase 7 already lists "Statistical comparison primitives (Wilson CI, paired bootstrap)" as post-V2.

---

### E.33. Dataset versioning — explicitly not a V2 concept; datasets evolve

**Decision:** V2 does not version datasets, snapshot them, or pin EvalRuns to a "dataset version." **Datasets evolve by design** — adding new EvalInputs is normal and expected. The mental model: comparison is always between run_configs at *current* dataset state. The signal that "this run_config hasn't kept up with the current dataset" is `percent_complete < 1` (per E.18 aggregation), surfaced in the UI. Backfilling existing run_configs against newly-added EvalInputs is the natural workflow.

**Why this works without versioning:**
- **EvalConfigs are immutable** (per E.17 / Kiln's `KilnParentedModel` convention) — every persisted score is permanently linked to the exact config that produced it.
- **EvalRuns pin to specific inputs** via `eval_input_id` (per A2.6) — each persisted score knows exactly which input it was scored against.
- **EvalInputs are self-contained by design** — each EvalInput carries all the data it needs for an eval run (input + reference), copied in at creation time; runs don't live-read from any upstream source. So per-input reproducibility holds independently. *(This was originally argued via F.2's snapshot semantics; F.2 was un-locked with Batch F on 2026-06-03, but the self-contained-by-design property stands on its own.)*
- **On-read aggregation against current dataset** is always apples-to-apples — every config is compared on the same now-current item set, with `percent_complete` flagging gaps.

**What this rules out for V2.0:**
- `dataset_snapshot_id` field on EvalRun (rejected — solves a non-goal).
- A `DatasetVersion` / `DatasetSnapshot` entity (rejected — Braintrust-style; conflicts with file-per-record + local-first).
- "Show me the dataset as of run X" UX (rejected — explicitly NOT a V2 product goal).

**Why "datasets evolve" is the right principle:**
- Users want **current eval scores**, not historical snapshots of out-of-date scores. If the dataset grows, the eval should keep up; old scores against an old dataset are misleading rather than informative.
- The "55 cases vs 47 cases" apples-to-oranges problem kintsugi solves with `matched_intersection()` (deferred per E.21) is different: that compares two *configs* on the same now-current dataset, not the same config across two historical dataset states.
- Git already handles "I really want to see the dataset as of last Tuesday" for power users — Kiln doesn't reinvent VCS.

**Application of A0:**
- [A0.4](#a04-local-first-pyinstaller-bundle-stays-clean) — no new entity, no new files; local-first storage stays simple.
- [A0.6](#a06-doesnt-exist-today-is-design-space-not-a-gap-to-patch) — applied inversely: "Braintrust has it" is not a reason for Kiln to have it. Different distribution model (cloud experiment-tracking vs local file-per-record), different product principle.

**Unblocks:** Nothing new — V2.0 ships without dataset versioning by design. `design/90_open_risks.md` documents this as an explicit non-goal (so future readers don't mistake the absence for an oversight).

**Plan deltas:** Remove "Dataset versioning / snapshots" from PLAN.md Phase 7 deferred list — this isn't a deferred feature, it's an explicit non-goal.

---

### E.36. Plugin extensibility — closed catalog + `code_eval` escape hatch for V2.0

**Decision:** V2.0 ships a **closed `V2EvalType` enum + `V2EvalConfigProperties` discriminated union** — adding a new built-in EvalConfigType requires a PR to Kiln. `code_eval` (per B.12) is the per-project Python escape hatch for cases the closed catalog doesn't cover. Inspect-style pip-installable third-party plugins are NOT shipped in V2.0; the option is preserved (not foreclosed) for V2.x if cross-project scorer-sharing becomes a demonstrated need.

**Why closed for V2.0:**
- [A0.4](#a04-local-first-pyinstaller-bundle-stays-clean) — Kiln's primary distribution is the PyInstaller bundle. The bundled binary cannot `pip install` at runtime, which is the prerequisite for setuptools-entry-point-based plugins (Inspect's model, `reports/competitive_inspect_ai.md:330-348`). An open registry would only work for users running pip-installed Kiln, creating a two-tier ecosystem.
- Builder UX (Batch G) needs to know about the full type catalog at build time. Third-party plugins discovered at runtime can't be surfaced cleanly by the goal-first questionnaire.
- Closed catalog avoids security review burden on arbitrary third-party scorers and keeps quality consistent for V2.0 launch.

**Why `code_eval` is sufficient escape hatch:**
- Per B.12, `code_eval` provides user-authored Python scoring inside a project. Anything a third-party plugin could do (custom signal extraction, project-specific logic, novel scoring) can be done inside `code_eval`.
- Limitation accepted: `code_eval` is per-project; no built-in mechanism to share a scorer across projects. If users want to share, they share the code (copy-paste, internal repo, etc.) — same way they share prompts and templates today.

**Why preserve the option (don't foreclose):**
- A2.1's discriminated union is structurally extensible — adding new `V2EvalType` enum values + properties classes is the same pattern third-party plugins would use. The architecture doesn't need to change to open up later.
- A2.11's adapter registry dispatches V2 by `properties.type` — entry-point discovery would slot in as an additional lookup path without changing the existing dispatch logic.
- If V2.x demand for cross-project scorer-sharing materializes, an open registry can be added targeting the pip-installed Kiln distribution (developers, CI) without affecting the bundled app.

**Design file responsibility:** `design/80_extensibility_contract.md` documents:
- The V2.0 closed-catalog stance and rationale.
- The architectural seams that would need to open for a future plugin model (entry-point registration, namespace-aware type lookup, builder UX discovery handling for runtime-discovered types).
- Why `code_eval` covers V2.0's long-tail use cases.
- This is a "leave the door unlocked, don't walk through it" design — the seams exist; we just don't ship the keys.

**What this rules out for V2.0:**
- Setuptools entry-point-based type registration.
- Runtime discovery of third-party `V2EvalType` values.
- Plugin marketplace / discovery UX.

**Application of A0:**
- [A0.3](#a03-config-first-code-is-an-escape-hatch-if-the-sandbox-story-closes) — `code_eval` is the principled escape hatch; closed catalog reinforces config-first.
- [A0.4](#a04-local-first-pyinstaller-bundle-stays-clean) — primary driver of the closed-for-V2.0 stance.

**Unblocks:**
- `design/80_extensibility_contract.md` — primary detail.
- Batch G builder UX — works against a known finite type catalog (per A2.4 launch surface).
- Stage 6 Phase 0 — no plugin-loading infrastructure required.

**Plan deltas:** None. PLAN.md Phase 7 implicitly supports this (no plugin-registry work scheduled).

---

## Batch E — Closed (2026-06-01)

All seven decisions locked: E.17 (no change), E.18 (skip persistence + n_used/n_excluded), E.19 (composite policy deferred), E.20 (tier deferred), E.21 (statistical primitives deferred on-read-only), E.33 (dataset versioning non-goal), E.36 (closed catalog + code_eval). Real schema impact: one new optional enum field on EvalRun (`skipped_reason`). All other decisions are explicit non-changes, deferrals, or design-file authoring directives.

---

## Batch K — Builder integration (V2 EvalConfig production paths)

**Surfaced 2026-06-01** via builder-integration blast-radius sub-agent during Batch B2 walk. V2 planning previously treated the builder as a UX redesign problem (Batch G) but missed the mechanical work to make the existing spec-builder and manual eval UI produce V2 EvalConfigs at all. K is **not a builder upgrade** — user-facing behavior is unchanged. K migrates the persistence path to V2 only.

### K.1. Manual eval config endpoint — V2-shape internally, focused API surface

**Decision:** `POST /create_eval_config` (`eval_api.py:859-880`) keeps its existing focused, LLM-judge-specific request shape — no generalization to a V2 properties union (premature for an API that may later add per-type endpoints). Request body: `name`, `model_name`, `provider`, `eval_steps`, `task_description`, `g_eval_mode: bool` (replacing V1 `type: EvalConfigType`). Handler internally constructs `EvalConfig(config_type="v2", properties=LlmJudgeProperties(g_eval=request.g_eval_mode, model_name=request.model_name, model_provider=request.provider, eval_steps=..., ...))` with [D.4](#d4-d4-v1-bc-llm_judge-detail-locked) defaults for `system_prompt` / `thinking_instruction`. URL unchanged.

**Rationale:** API shape ≠ datamodel shape. The endpoint stays LLM-judge-focused because that's what it creates; when new V2 types get UI in the follow-up project, they get their own focused per-type endpoints. The `g_eval_mode` field preserves the V1 UI's g_eval option in V2 form ([A2.2](#a22-unify-g_eval-and-llm_as_judge-under-v2-llm_judge-with-g_eval_mode-bool-flag) unifies under `llm_judge` with the `g_eval_mode: bool` flag).

**Application of A0:** [A0.1](#a01-backwards-compatibility--v2-reads-v1-v2-never-migrates-v1) — existing V1 EvalConfigs on disk continue to load via the legacy path; the endpoint redesign affects only how new EvalConfigs are *created* going forward.

**Unblocks:** K.5 frontend payload. Batch H Phase 0 (API additive schema).

---

### K.2. Copilot path — local V1→V2 translation; remote `api.kiln.tech` unchanged

**Decision:** `copilot_api.py:337-340` is updated to construct V2 EvalConfigs from V1-shaped Copilot responses. Field mapping (verified 2026-06-01 sub-agent): `model_name` / `model_provider` / `eval_steps` / `task_description` direct from response; `g_eval_mode=False` always (Copilot always produces non-g_eval); `system_prompt` / `thinking_instruction` via [D.4](#d4-d4-v1-bc-llm_judge-detail-locked) defaults; V1 free-form prompt → V2 Jinja2 `prompt_template` via local wrapping. **No remote `api.kiln.tech` changes in this project.**

**Phased remote evolution (post-V2 follow-up, tracked in OPENS.md Builder section):** remote `api.kiln.tech /v1/copilot/generate_batch` output-generation step becomes optional, then default-off, then dropped. Old Kiln clients (which expect outputs to populate TaskRuns) must upgrade before the remote drops outputs.

**Implementation detail deferred to Stage 5 `design/21_type_llm_judge.md`:** exact Jinja2 wrapping shape (which reserved variables from [D.2](#d2-templating--extraction-reframed-to-general-kiln-capability-round-2-2026-05-26) get embedded, scaffolding format, `required_var` derivation rule, per-criterion structured output coupling).

**Unblocks:** K.5 frontend (Copilot side is server-handled). B2 framing (together with K.3, substantially narrows the option space).

---

### K.3. V2 dataset generation — V2-only EvalConfigs; dataset shape per flow

**⚠ Amended 2026-06-01 by Batch B2 closure.** The original lock framing ("Eval-dataset generation persists EvalInputs only") was based on the incorrect assumption that the Copilot flow doesn't create golden datasets. Sub-agent verification 2026-06-01 confirmed Copilot creates golden TaskRun subsets today (`copilot_utils.py:246-299`, `copilot_api.py:321-333`). **See B2.1 below and the "B2 closure — dataset shape per flow" table for the final, correct shape.** This section retains its V2-only EvalConfig stance; only the dataset-shape sub-claim was wrong.

**Decision (corrected):** After this project ships, the spec_builder and manual eval config UI produce **only V2 EvalConfigs**. Dataset shape varies per flow (see the per-flow table in the B2 section): Copilot's eval set is EvalInput-shaped (V2); Copilot's golden subset and the entire manual flow's datasets stay TaskRun-shaped (V1, unchanged). The `EvalConfigType.g_eval` and `EvalConfigType.llm_as_judge` enum values remain in the codebase to read existing V1 records on disk (per [A0.1](#a01-backwards-compatibility--v2-reads-v1-v2-never-migrates-v1)), but **no new V1 EvalConfig records are created** via these paths.

**Synth-screen-for-fine-tuning is orthogonal and unchanged.** Fine-tuning still requires TaskRuns with outputs; that mode of the synth screen is not touched by this project.

**Manual flow synthetic data UI is also unchanged** — manual evals continue producing TaskRuns for eval set AND golden subset via the existing synth UI/APIs. V2 EvalConfigs consume this TaskRun-source data via the B2.1 runtime translation path.

**EvalConfig creation is V2-only (this part of the original lock stands).** Coexistence (per A0.1) is read-only at the EvalConfig persistence layer.

**Implication for Batch B2 (informational; B2 not yet resolved):** narrows B2 substantially toward Option 2 (deprecate `eval_config_eval` for new evals; existing V1 `eval_config_eval` paths continue functioning for existing V1 evals only via on-disk reads).

**Unblocks:** B2 closure (with significantly narrowed option space). Stage 5 `design/45_runner_architecture.md` (V2 dataset-creation contract). Stage 5 `design/10_data_model.md` (EvalInput as sole V2 eval-dataset entity).

---

### K.4. SpecType → V2EvalType mapping — all 17 SpecTypes to `llm_judge`

**Decision:** For this project, the spec_builder and manual eval config UI produce only V2 `llm_judge` configs. All 17 SpecTypes in `libs/core/kiln_ai/datamodel/spec_properties.py:10-38` map to `V2EvalType.llm_judge`. Mapping additional SpecTypes to other V2 types (e.g., `appropriate_tool_use → tool_call_check`) is deferred to the post-V2 "new eval types in UI" follow-up project.

**SpecType is independent of `g_eval_mode`** (verified 2026-06-01 sub-agent). SpecType describes the evaluation domain / template content focus; `g_eval_mode: bool` describes the judge algorithm and is picked independently in the UI flow (`create_eval_config/+page.svelte:161-180` — Step 2 radio; default determined by model `supports_logprobs` per `+page.svelte:360`, not by SpecType). The Copilot path always produces non-g_eval (`copilot_api.py:340`).

**Framing:** Not a builder upgrade — SpecType selection UX is untouched; only the persisted EvalConfig shape is V2.

**Unblocks:** Batch G decision 30 (hidden SpecTypes) is independent of K.4 mapping (all 17 → `llm_judge` regardless of UI visibility).

---

### K.5. Frontend V2 payload — minimal mechanical updates

**Decision:**
- `spec_builder/+page.svelte` and `spec_builder/+page.ts`: **no-op** (verified 2026-06-01 sub-agent). Server (`copilot_api.py`) handles all V2 EvalConfig construction; frontend passes Copilot state through opaquely (`judge_info` and `sdg_session_config` are opaque payloads).
- `create_eval_config/+page.svelte:200`: adjust the POST payload to drop the V1 `type: EvalConfigType` field and pass `g_eval_mode: bool` instead (per K.1).
- `eval_steps_utils.ts` and `spec_templates.ts`: may need minor prompt-content tweaks consistent with V2 Jinja2 template format (cross-refs Batch D; template content migration is owned by D.1/D.2, K.5 only commits the SvelteKit form to use the V2 payload shape).

**Unblocks:** Stage 6 frontend implementation for the V2 builder paths.

---

## Batch K — Closed (2026-06-01)

All five decisions locked: K.1 (manual endpoint LLM-judge-focused, V2-internally), K.2 (Copilot local V1→V2 translation; no remote changes), K.3 (V2-only EvalConfig creation; dataset shape per flow — amended 2026-06-01 by B2.1), K.4 (all 17 SpecTypes → `llm_judge`; SpecType orthogonal to `g_eval_mode`), K.5 (minimal frontend tweaks; spec_builder is a no-op). **Framing across all five: K is not a builder upgrade.** User-facing behavior is unchanged; persistence and internal handler logic migrate to V2. Two sub-agent verification reports backed the lock (2026-06-01: builder-integration blast radius, and field-mapping + orthogonality verification).

---

## Batch B2 — Golden dataset shape for V2 EvalConfigs (Closed 2026-06-01)

### B2.1. V2 EvalConfig + TaskRun source — runtime translation

**Decision:** Adds a runtime translation path so V2 EvalConfigs can consume V1 TaskRun-source data. At job-collection time in `eval_runner.py` (`collect_tasks_for_eval_config_eval` at `eval_runner.py:102-132` and the analogous `task_run_eval` collector), when the EvalConfig has `config_type == "v2"` and the source is TaskRun-shaped (via `eval_set_filter_id` or `eval_configs_filter_id`), the runner synthesizes an in-memory `EvalInput` from each TaskRun for V2 adapter consumption.

**Translation mapping:**
- `TaskRun.input` → `SingleTurnEvalInputData.user_message.text`
- `TaskRun.tags` → `EvalInput.tags`
- `TaskRun.output.output` → carried as runner side-channel (`stored_output` on `EvalJob`) for `eval_config_eval` mode; passed to the V2 adapter via the D.2 reserved variable mechanism
- `TaskRun.trace` → passed to adapter as the D.2 reserved `trace` template variable
- `TaskRun.id` → **not carried.** (Originally mapped to `source_task_run_id` per F.1, but that field was un-locked/deferred with Batch F on 2026-06-03 — `EvalInput` ships without it in V2. The synthesized EvalInput is in-memory/runtime-only anyway, so provenance linkage is moot here.)
- `TaskRun.output.rating` → **stays on TaskRun**; the correlation API at `eval_api.py:1250-1367` continues reading ratings from TaskRun and judge scores from EvalRun unchanged. The V2 adapter never sees the rating (matches V1's existing pattern — verified that `g_eval.py` never imports `TaskOutputRating`).

**EvalRun source field for V2 EvalConfig + TaskRun-source runs:** `EvalRun.dataset_id` points at the source TaskRun (per [A2.6](#a26-evalrun-coexistence--keep-eval_config_eval-bool-add-eval_input_id-as-orthogonal-source-field)). This is what lets the correlation API pair (TaskRun rating, EvalRun judge scores) for V2 EvalConfig runs without modification.

**[C.runner.3](#crunner3-evalrunner__init__--extend-constructor-validation-to-accept-evalinput-sourced-runs-alongside-taskrun-sourced-runs) coverage matrix amendment — new row:**

| Source | Run mode | `run_configs` | Data flow |
|---|---|---|---|
| TaskRun (V1 filter, `eval_set_filter_id` or `eval_configs_filter_id`) — **V2 EvalConfig** | either | per mode | **NEW** — runner synthesizes in-memory EvalInput per TaskRun; V2 adapter consumes EvalInput shape; `EvalRun.dataset_id` points at source TaskRun |

**Edge cases:**
- Multi-turn TaskRuns (with `parent_task_run_id`) → skip via [C.runner.1](#crunner1-missing-reference-data--skip--report) with `incompatible_input_shape` reason (per [E.18](#e18-skip-persistence--n_usedn_excluded-surfacing--additive-evalrun-field-no-persisted-aggregate) skip enum).
- TaskRun with no rating → calibration excludes downstream (no skip; judge still produces scores).
- Multi-turn V2 EvalConfigs (`MultiTurnSyntheticEvalInputData` consumers) under V1 TaskRun source → no V1 multi-turn shape to translate from; skip with `incompatible_input_shape`. Multi-turn V2 evals rely on Copilot/Pro alignment phase (no V1 multi-turn calibration capability).

**No bind-time validator** preventing V2 EvalConfig under V1-filter Eval. The translation path makes the combination work end-to-end; the validator gap surfaced during B2 walk (no Eval ↔ EvalConfig consistency check) becomes "by design" given this decision.

**[A2.3](#a23-evaluation_data_type-becomes-per-evalconfig-in-v2-legacy-field-made-optional-on-eval) reverse-direction validator gap** (V1 EvalConfig under V2 Eval) **remains a real gap** but is moot in practice — [K.3](#k3-v2-dataset-generation--evalinputs-only-legacy-creation-paths-removed) ensures no new V1 EvalConfigs are created via any flow. Validator can be added if extra hygiene is wanted; not blocking V2 launch.

**Application of A0:** [A0.1](#a01-backwards-compatibility--v2-reads-v1-v2-never-migrates-v1) — preserves V1 TaskRun-based calibration mechanism for V2 EvalConfigs without modifying V1 storage shape or V1 adapter contracts.

**Implementation scope:** ~60 LOC sub-agent estimate. `EvalJob` carries `item: TaskRun | EvalInput` union + optional `stored_output: str | None`. Runner translation in `collect_tasks_*` methods. `run_job` dispatches based on `isinstance(job.item, EvalInput)`. **No V2 adapter changes, no new EvalRun fields, no new schema fields, no new skip-reason values beyond E.18's existing set.**

**Unblocks:** Closes Batch B2. Manual eval creation flow remains functional with V2 EvalConfigs without forcing a synthetic data UI redesign. Copilot golden subset calibration works for V2 EvalConfigs. Stage 5 `design/45_runner_architecture.md` gains a focused section on the translation path.

---

### B2 closure — dataset shape per flow (K.3 amendment context)

Resolving B2 with the translation path requires amending K.3's "EvalInputs only" stance. The Copilot path was verified 2026-06-01 to create golden TaskRun subsets today (`copilot_utils.py:246-299` `create_dataset_task_runs`, with `Eval.eval_configs_filter_id = "tag::eval_golden_{name}"` wired at `copilot_api.py:321-333`). The earlier "Copilot doesn't need golden datasets" framing was incorrect — Copilot's wizard alignment phase and golden subset are complementary, not alternatives.

**Final dataset shape per flow (amends K.3):**

| Flow | Eval set | Golden subset | Train set | Filter fields populated on Eval |
|---|---|---|---|---|
| **Copilot path** | EvalInputs (V2) | TaskRuns (V1, unchanged) | TaskRuns (V1, unchanged) | `eval_input_filter_id` + `eval_configs_filter_id` |
| **Manual path** | TaskRuns (V1, unchanged) | TaskRuns (V1, unchanged) | TaskRuns (V1, unchanged) | `eval_set_filter_id` + `eval_configs_filter_id` |
| **Synth-screen-for-fine-tuning** | n/a | n/a | n/a (TaskRuns produced for fine-tuning, orthogonal to evals) | n/a |

**EvalConfig type in both flows:** always V2 (`config_type="v2"`, per [K.3](#k3-v2-dataset-generation--evalinputs-only-legacy-creation-paths-removed)'s preserved "no new V1 EvalConfigs" stance).

**Why this works:** [A2.9](#a29-eval_set_filter_id-becomes-optional-with-mutual-exclusivity-validator)'s mutex is between `eval_set_filter_id` and `eval_input_filter_id` only — `eval_configs_filter_id` (golden) is independent and TaskRun-typed in both flows. The runtime translation per B2.1 handles V2 EvalConfig consumption of TaskRun-source data.

**Future migration (tracked in OPENS.md):** Manual flow may migrate to EvalInput-source eval datasets post-V2 (would require synthetic data UI redesign). Explicitly **not** in scope for this project per Steve's direction.

---

## Batch B2 — Closed (2026-06-01)

Resolved with Option 1a (runtime translation). B2.1 locks the translation mechanics; K.3 amended above to reflect the actual per-flow dataset shape. One sub-agent verification report backed the translation design (2026-06-01: TaskRun→EvalInput translation feasibility + V1 calibration rating-flow analysis). Critical mid-walk finding: Copilot path creates golden TaskRun subsets today (sub-agent verified at `copilot_utils.py:246-299` and `copilot_api.py:321-333`), invalidating the earlier "Copilot doesn't need golden" framing that K.3 was originally locked under.

---

## Batch J — Agent eval expansion (Closed 2026-06-02)

Two independent additions that bring V2.0 agent-eval coverage from 1 of 4 industry categories (trajectory only, existence-check) to 4 of 4 — parity with Promptfoo's trajectory assertion set. Both are config-driven deterministic trace inspectors (no LLM call, no code execution, no sandbox). Detail doc: `batch_agent_eval_expansion.md`. Stage 5 design home: `design/22_type_deterministic_basics.md`. Trace structure verified against actual Kiln source (`kiln_new/libs/core/kiln_ai/`) 2026-06-02: trace is an OpenAI-format `list[ChatCompletionMessageParam]` on `TaskRun.trace`; roles are system / user / assistant / tool; multi-turn is modeled via `parent_task_run_id` chaining (no formal `turn` field — a leaf TaskRun's trace holds the full accumulated conversation).

### J.37. `tool_call_check` properties expansion

**Decision:** Expand the already-locked `tool_call_check` type's properties (no catalog change) to cover tool trajectory checks — existence, ordering, forbidden-tool, and per-argument matching. Locked shape:

```python
class ArgMatch(BaseModel):
    value: JsonValue
    match_mode: Literal["exact", "contains", "regex"] = "exact"

class ToolCallSpec(BaseModel):
    tool_name: str
    expected_args: dict[str, ArgMatch] | None = None  # None = ignore args

class ToolCallCheckProperties(BaseModel):
    type: Literal["tool_call_check"] = "tool_call_check"
    expected_tools: list[ToolCallSpec]
    match_mode: Literal["any", "all", "ordered", "never"] = "all"
    on_unexpected_tools: Literal["ignore", "fail"] = "ignore"
```

**`match_mode` semantics:**
- `any` — at least one expected tool was called (subset match).
- `all` (default) — every expected tool was called at least once, any order.
- `ordered` — expected tools appear in the listed sequence (other calls between them are OK unless `on_unexpected_tools="fail"`).
- `never` — **fail if any of `expected_tools` was called** (respecting `expected_args` if set). Blocklist semantics — "agent must never call `delete_database`", or "must not call `search_web` with `query` matching a PII pattern". Under this mode `expected_tools` reads as "forbidden tools"; field name kept, documented rather than branched.

**`arg_match_mode` moved to per-arg.** The top-level `arg_match_mode` from the original proposal is removed — one mode across every arg of every tool was too wide. Each expected arg carries its own `match_mode` via `ArgMatch` (`value` + `match_mode`), so a single call can mix `contains` on `query` with `exact` on `user_id`.

**Deferred to Stage 5 design (`design/22`):** a scalar-shorthand union for `expected_args` (`JsonValue | ArgMatch`, where a bare scalar means `exact`) to reduce verbosity in the common exact-match case. This is a serialization nicety, not a semantics change — locked shape above is the canonical form.

**Rationale:** Covers Promptfoo's `trajectory:tool-used` / `tool-sequence` / `tool-args-match` (3 of 5 trajectory assertions) plus a forbidden-tool capability Promptfoo lacks, in one typed schema. No new type, no catalog change.

**Default `match_mode = "all"`:** "I named these tools, all of them are required" is the clearest mental model; `any` would invite "why does my check pass when it called the wrong tool?"

**Unblocks:** Stage 5 `design/22_type_deterministic_basics.md` (properties schema + adapter: existence / ordering / never / per-arg matcher). Implementation ~150 LOC, Phase 1.

---

### J.38. `step_count_check` — new EvalConfigType

**Decision:** Add `step_count_check` as the 7th V2.0 catalog entry (A2.4 amended above). Closes the agent-eval efficiency category. Locked shape:

```python
class StepCountCheckProperties(BaseModel):
    type: Literal["step_count_check"] = "step_count_check"
    count_type: Literal["tool_calls", "model_responses", "turns"]
    min_count: int | None = None
    max_count: int | None = None

    @model_validator(mode="after")
    def check_bounds(self):
        if self.min_count is None and self.max_count is None:
            raise ValueError("step_count_check requires at least one of min_count / max_count")
        if (self.min_count is not None and self.max_count is not None
                and self.min_count > self.max_count):
            raise ValueError("min_count must be <= max_count")
        return self
```

**`count_type` semantics (verified against actual trace shape 2026-06-02):**
- `tool_calls` — count of individual tool-call requests across assistant messages ("how many calls the agent made").
- `model_responses` — count of assistant-role entries in the trace (one per LLM response; an assistant message that requests N tool calls counts as **1**). Renamed from the proposal's `messages` — "messages" was ambiguous (excluded user messages, included tool messages, unclear on the multi-tool-call case). `model_responses` names exactly what it counts.
- `turns` — count of user-role entries in the trace (one per user→assistant exchange). Single-turn evals always count as **1**; only meaningful when the source is multi-turn. Grounded in the `parent_task_run_id` chaining model.

`model_responses` and `turns` do **not** collapse: a single-turn agent run with 2 sequential tool calls has `model_responses=3`, `turns=1`, `tool_calls=2`. They only coincide in the degenerate no-tools single-turn case.

**Validator:** at least one bound must be set (no all-None no-op config); `min_count <= max_count` when both set.

**Single-turn + `count_type="turns"`:** valid (not skipped) — counts 1; `max_count=1` passes trivially, which is the correct answer for "must be one-shot". Skipping would be surprising.

**`tokens` count_type:** out of scope for V2.0 — token count is cost-evaluation territory, conceptually distinct from step efficiency. Revisit post-V2 if users ask. Not foreclosed (additive enum value).

**Rationale:** Covers Promptfoo's `trajectory:step-count`. ~20 LOC schema + ~50 LOC trace-walker adapter, Phase 1.

**Unblocks:** Stage 5 `design/22_type_deterministic_basics.md` (new type entry in `V2EvalType` enum + properties class + adapter). Brings V2.0 to agent-eval category parity with Promptfoo.

---

## Batch J — Closed (2026-06-02)

Both decisions locked: J.37 (`tool_call_check` properties expansion — `match_mode` any/all/ordered/**never**, per-arg `ArgMatch`, top-level `arg_match_mode` removed) and J.38 (new `step_count_check` type — `count_type` tool_calls/**model_responses**/turns, min/max with validator). Schema impact: one new `V2EvalType` enum value (`step_count_check`) + one new properties class; `ToolCallCheckProperties` shape expanded. Steve-driven refinements during the walk: per-arg arg-matching (was top-level), added `never` mode, renamed `messages`→`model_responses`, added min/max validator. Trace-structure question (`messages` vs `turns` collapse?) resolved by sub-agent verification against actual Kiln source — they are genuinely distinct. Detail doc `batch_agent_eval_expansion.md` updated to locked shapes; archive once `design/22_type_deterministic_basics.md` is authored in Stage 4.

---

## Batch G — Expose V2 eval types in the UI (create + view) (Closed 2026-06-03)

**Rescope (the framing decision).** Batch G was originally "Builder UX redesign" (goal-first questionnaire + routing). That is **cut from evals V2** and handed to a future standalone onboarding project. The "describe your goal in plain text, we pick and size the eval for you" front door is a UX project in its own right and would put the core infra delivery (extensible eval types, deterministic checks, code evals) at the mercy of UX iteration. Evals V2's UI obligation is narrower and necessary: **a minimal-but-complete UI to (1) create the new eval types and (2) view them in the existing surfaces** — otherwise V2 ships eval types that exist in the schema but are unreachable. Copilot is untouched (still the plain-language → LLM-judge path; stays `llm_judge`-only per K). Source-of-truth design file: `design/70_builder_and_onboarding.md` (create/view sections) + `design/27_type_code_eval.md` (code-eval editor/contract detail).

**Disposition of the original Batch G decisions:**
- **27 (goal-first questionnaire)** — DEFERRED to future onboarding project. Replaced in V2 by a direct **eval-type picker** (LLM judge recommended at top, then the rest).
- **28 (routing logic → type + dataset path + count)** — DEFERRED. Moot under a direct picker: the user chooses the type; the eval + dataset already exist by the time you add a config (datasets come from the existing SDG flow, untouched).
- **30 (hidden SpecTypes disposition)** — DEFERRED, no-op. K.4 maps all 17 SpecTypes → `llm_judge` regardless of UI visibility; nothing blocks.
- **34 (`eval_configs_filter_id` / golden-subset requirement relax)** — DEFERRED. Part of the cut "lower creation friction" goal; not infra-blocking.
- **A0.2 right-sizing mechanism** — DEFERRED (recorded at A0.2 above). The "many small evals" principle itself stands and outlives V2.

### G.1. Shared create container + pluggable per-type components

**Decision:** One create surface owns the shared mechanics; per-type components plug into it. Container responsibilities: load test data, **run the test (uniform `(config + input) → scores` call — backend adapter registry already dispatches by type, so test-run is generic, NOT per-component)**, own the Save button, own the clone/prefill path. Per-type component responsibilities: render its authoring form (left pane) and produce the `EvalConfig` properties to hand up for save; optionally supply a custom result renderer. The only per-type hook the container needs for running is `requiresTrust: bool` (true for code-eval → gates the run behind the trust modal). Layout is the standard Kiln left=main / right=details: left pane = the injected per-type authoring component; right pane = "Test Run" (pick a recent dataset item → run → results).

**Page altitude + naming:** The container sits at **config-creation altitude — under an existing Eval** (the Eval, its `output_scores`, and its dataset already exist via the manual/SDG flow). It is *not* an Eval creator and does not touch SDG/dataset generation. New page name reflects this (config-level, e.g. `create_eval_config`-style, not `create_manual_eval` which read as eval-level). The existing LLM-as-judge `create_eval_config/+page.svelte` becomes the **LLM-judge component** inside this container (its Save button removed, hooked to the container's).

**Output scores are Eval-level (settled by [C.9](#c9-eval--evalconfig-cardinality), not open).** `Eval.output_scores` is fixed before you add a config; every EvalConfig must produce all of them. The container passes `output_scores` to both the component and the test-run API; the test's return-shape check is "did the code/judge return every declared score name with a value valid for its type?" — well-defined, not free-form.

**No edit — clone only.** EvalConfigs are immutable for provenance (the `EvalRun → frozen EvalConfig` chain; [E.17](#e17-score-provenance--audit-trail)). "Edit a config" = **clone to a new candidate and modify** (existing Kiln clone pattern, reused). Saved configs are read-only; calibration compares candidates and promotes via `current_config_id`. Container supports prefill-from-existing for the clone path.

**Type-picker shows all V2 types, no applicability filtering.** `tool_call_check` / `step_count_check` etc. are listed regardless of whether the task uses tools or is multi-turn — checking a trajectory that happens to have zero tool calls is still a valid check. LLM judge recommended at top. Selecting a type pushes history / updates URL the SvelteKit-official way, so Back returns to the picker.

### G.2. Code-eval create UI (Beta)

**Decision:** Code evals are authored in the Kiln UI (not SDK-only) — a meaningful build, judged worth it. Specifics:
- **Editor:** CodeMirror 6, `@codemirror/lang-python` (Python-only, syntax highlighting, "Python" label top-left). **Lazy-loaded** — imported only on pages that need it, kept out of the default/bundled load. Loads with a minimal valid eval example. Built as a reusable component.
- **Format / lint buttons: CUT.** Not native to CM6 (would need a server-side ruff/black round-trip); not worth it for V2. Highlighting only.
- **Examples gallery:** "See examples" link → tabbed modal of a few common cases ("Parse JSON and compare fields", etc.), each with a "Use this template" button. (Content depends on the code-eval scorer contract — see note below.)
- **Test pane (right):** "Test Run" → "Input Section" lists recent dataset items to pick from; **manual free-text input is cut** (reference data available via an Advanced expander; trace comes from the selected dataset item). Run → new server API executes the code in the **same B.13 sandbox** with the same pre-save validators (limited imports) — it will not run anything it would not let you save — *previews* the result without persisting, and checks the return shape against `output_scores`. Async: spinner + **Cancel** (also satisfies the open runaway-code cancellation affordance). **Empty-dataset state:** "Run your task to generate sample inputs" — rare; in that state "Save Without Testing" is the only path.
- **Save gate:** a successful test run (code executed AND returned a valid shape matching `output_scores`) enables Save. Saving without a successful test → "Save Without Testing" confirm modal ("you're a great coder, but it never hurts to run it once"; red Save / Cancel).
- **Trust gate:** "Trust this code?" modal on first run or save ("never paste code from a stranger or the internet here"). Answer held **in-memory, window-scoped; re-asked next launch; no disk/DB persistence.** This locks the B.13 trust-gate-shape open at the conservative/ephemeral end.
- **Beta:** Beta label under the header **on code-eval only** — deterministic types (exact_match, pattern_match, contains, set_check, tool_call_check, step_count_check) ship stable.
- **P2 (not V2.0-gating):** "Ask assistant for help" button launching an assistant chat pre-seeded with "I need help writing a python-based eval…".

**Sequencing dependency:** the editor's "minimal valid example", the examples-gallery content, and the return-shape check all encode the **code-eval scorer signature** (what's injected — output / reference data / trace; what shape it returns). That contract is still open and owned by `design/27_type_code_eval.md` (helper-library surface, result serialization). The UI *shape* is locked here; the example *content* is filled in once the contract lands. Lock the scorer signature before finalizing gallery copy.

### G.3. View surfaces — per-type renderer registry + defensive enum binding

**Decision:** The eval/config view surfaces render per-type via a **renderer registry keyed on the same `properties.type` discriminator the backend adapter registry uses** (mirrors A2.11 / [C.11b](#c11b-v2-adapter-registry-architecture)). There are effectively two parallel front-end registries — **create-form-by-type** and **result-renderer-by-type** — best expressed as one per-type module exporting `{ label, icon, createForm, resultRenderer, requiresTrust }`, so a new type is one registered file. Mixed-type display (an Eval whose candidate configs are different types) must not choke the view. Detailed view-screen design deferred to Stage 5 per Steve (architecture locked here; layout later).

**Defensive coding:** the registry is **exhaustive over the `V2EvalType` enum** — compile-time (TS exhaustiveness / `never`) + runtime assert that every enum value has a registered module. A backend type added without a UI module fails loudly rather than rendering blank. Existing Kiln pattern; point it at the registry map.

---

## Batch G — Closed (2026-06-03)

Rescoped from "Builder UX redesign" to "Expose V2 eval types in the UI (create + view)." Original decisions 27/28/30/34 + the A0.2 right-sizing mechanism deferred to a future goal-first onboarding project (the fresh `competitive_ui_vs_code/` study is its reference brief). Locked: G.1 (shared pluggable create container at config altitude; container owns generic test-run + save; clone-not-edit; type-picker shows all types), G.2 (code-eval create UI — CodeMirror 6 lazy-loaded, sandboxed preview API, ephemeral window-scoped trust gate, Beta on code only; format/lint and manual test input cut), G.3 (per-type renderer registry keyed on `properties.type`, exhaustive over `V2EvalType`). Steve-driven during the walk: scope cut to infra+minimal-UI (not onboarding redesign); manual test input removed (dataset-item only); format/lint cut; clone model confirmed; Beta scoped to code-eval. Open dependency tracked: code-eval scorer contract (`design/27_type_code_eval.md`) gates the examples-gallery content, not the UI shape.

---

## Batch H — Coexistence + code reuse (Closed 2026-06-03)

The final alignment batch. Decision brief (code-grounded against `~/Dropbox/workspace/kiln_new`): `batch_h_coexistence_and_builder.md`.

### H.32. EvalInput/TaskRun coexistence — confirmation, no new lock

**Decision:** No new coexistence decision required. A code-grounded sweep enumerated **12** actual TaskRun↔eval-pipeline coupling points (reports estimated "6+"); all 12 are already covered by previously locked decisions — A2.5 (DatasetFilter vs EvalInputFilter), A2.6 (EvalRun input-source field + validator), A2.9 (`eval_set_filter_id` optional), A2.10 (model-field helper), A2.11 (registry signature), C.runner.2 (`validate_output_fields` V2 bypass), C.runner.3 (`EvalRunner.__init__` branch), C.11c (generic `BaseEval`), B2.1 (runtime TaskRun→EvalInput translation), D.5 (V1 GEval never changed). The one residue — `BaseEval.run_eval`'s abstract signature widening from `TaskRun` to `TaskRun | EvalInput` — is a mechanical consequence of B2.1, not a new design decision.

**Unblocks:** Confirms `design/15_v1_v2_coexistence.md` coverage is complete (no new refs). The signature widening is recorded in `design/45_runner_architecture.md`.

### H.32a. Legacy/V2 adapter code reuse — extract pure scoring helpers; build V2 judge fresh; never refactor legacy

**Decision:** Extract GEval's three V1-decoupled, pure scoring seams — structured-output score parsing (`build_llm_as_judge_score`), the G-Eval token-logprob pipeline (`build_g_eval_score` + `g_eval_single_metric` / `rating_token_to_score` / `raw_output_from_logprobs` / `metric_offsets` / `token_search_range`), and the rating-token map (`score_from_token_string` + `TOKEN_TO_SCORE_MAP`) — into a shared helper module (e.g. `kiln_ai/adapters/eval/scoring_utils.py`). GEval imports them with **zero behavior change**. The V2 `llm_judge` adapter is built fresh on those helpers + `BaseEval.build_score_schema()` + the D.2/D.3/D.4 Jinja2 / `JinjaInputTransform` infra, reading model fields from its own `LlmJudgeProperties`. GEval's two V1-coupled seams (the three `generate_*_run_description` f-strings; the `GEvalTask` construction) are NOT shared. Rejected: generalizing GEval in place (violates [D.5](#d5-v1-backwards-compatibility--absolute)); a full legacy rewrite now (violates [A0.1](#a01-backwards-compatibility--v2-reads-v1-v2-never-migrates-v1)). Builds on the [A2.10](#a210-model_and_provider-helper-extraction-baseeval-stays-generic) helper as the established seam.

**Prerequisite (hard gate before any extraction):** GEval's `reference_answer` path has **zero test coverage** (verified 2026-06-03 — `generate_ref_ans_run_description` and the `reference_answer` branch of `run_eval` have no tests across `test_g_eval.py` / `test_eval_runner.py` / `test_g_eval_data.py`). Two characterization tests (~50 LOC) pinning current behavior must land as a standalone commit before helpers are extracted. Already seeded in PLAN.md Phase 0 "Characterization tests."

**Deferral boundary (explicitly NOT touched pre-launch):** GEval's prompt f-strings, `GEvalTask`, `GEval.__init__`, and `GEval.run_eval` beyond the A2.10 extraction. No V1 adapter behavior change of any kind.

**Unblocks:** Phase 1 `llm_judge` adapter; `design/45_runner_architecture.md` adapter-sharing section; `design/21_type_llm_judge.md` (scoring helper consumption). Helper extraction parallelizes with Phase 0 schema work.

### H.29. Spec builder reliability — OUT OF SCOPE for evals V2

**Decision (Steve, 2026-06-03):** Spec builder / Copilot generation reliability (the ~10-min 300-example single sync request; batch-size / streaming / partial-progress / async fixes) is **unrelated to evals V2 and out of scope for this project.** Not a V2 deliverable; not implemented or modified as part of evals V2. The brief's analysis (300 = 15×20 hardcoded at `copilot_utils.py:43-44`; single sync call; existing `CancellableStreamingResponse` infra Kiln could ride on) is retained in `batch_h_coexistence_and_builder.md` for whoever picks up builder reliability later, but evals V2 does not own it. Decision 29 removed from the evals-V2 inventory; PLAN.md Phase 2 "Spec builder reliability" dropped from V2 scope.

**Note:** Does NOT affect K.1/K.2/K.3/K.5 (builder *mechanical integration* to produce V2 EvalConfigs/EvalInputs), which remain in scope — that's correctness of output shape, not generation reliability.

---

## Batch H — Closed (2026-06-03)

Final alignment batch. H.32 = coexistence confirmation (12 real coupling points, all covered by prior locks; lone residue is the mechanical `run_eval` signature widening, owned by `design/45`). H.32a = extract GEval's pure scoring helpers (score parsing + logprob pipeline + token map) into `scoring_utils.py`, build V2 judge fresh on them + D.2/D.3/D.4, never refactor legacy GEval; hard prereq = two characterization tests for the untested `reference_answer` path. H.29 (spec builder reliability) ruled OUT OF SCOPE by Steve — unrelated to evals V2, removed from scope, not implemented. **With Batch H closed, all Stage 3 alignment batches are locked.**


