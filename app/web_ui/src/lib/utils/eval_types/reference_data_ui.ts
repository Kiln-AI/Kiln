/**
 * Gates the manual reference-key inputs, and the reference-data copy and starter-code
 * variants that go with them, across the judge forms, the type metadata and the
 * builder's test-before-save gate. Nothing in the UI populates reference data under an
 * arbitrary key the user names by hand, so a judge configured that way would find
 * nothing to read at run time. Library users are unaffected. Grep the flag for the
 * current set of sites rather than trusting a list here.
 *
 * Not a gate on reference data as a whole: an llm_judge's reference-data input resolves
 * from the judge itself (`referenceDataUsageMode` in `registry.ts`) and is offered
 * whatever this flag says, because the server declares that judge's key and the runner
 * populates it for TaskRun-backed items.
 *
 * Flip to `true` to restore the gated affordances. Those code paths are kept intact and
 * type-checked so that flip is the only change required.
 */
export const SHOW_REFERENCE_DATA_UI: boolean = false
