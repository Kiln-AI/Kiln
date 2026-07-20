/**
 * Reference data (expected values attached to an eval input) is fully functional
 * in the library, API and eval runners. However, the synthetic data gen flows
 * can't yet attach reference data to an eval set, so a judge built against it in
 * the UI would have nothing to read at run time.
 *
 * Until data gen can produce reference data, every reference-data affordance is
 * hidden from the UI behind this flag. Library users are unaffected.
 *
 * Flip to `true` to restore the UI. The gated code paths are kept intact and
 * type-checked so that flip is the only change required.
 */
export const SHOW_REFERENCE_DATA_UI: boolean = false
