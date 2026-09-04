import type { ModelDetails } from "$lib/types"

export interface ModelDropdownSettings {
  // Filter out all the models that do not match the predicate
  filter_models_predicate: (model: ModelDetails) => boolean
  requires_structured_output: boolean
  requires_data_gen: boolean
  requires_logprobs: boolean
  requires_uncensored_data_gen: boolean
  requires_doc_extraction: boolean
  requires_tool_support: boolean
  suggested_mode:
    | "data_gen"
    | "evals"
    | "uncensored_data_gen"
    | "doc_extraction"
    | null
}

// Whether the "we suggest a Recommended model" advisory renders under a model
// dropdown. Quiet callers (forms with several model lanes, where one advisory
// per lane is noise) drop it only in the state that tells the user nothing
// new: a chosen model that already is suggested. The states that carry
// information — no model chosen yet, or a model that is not suggested — always
// render.
//
// `suggestion_known` is false while the model list is still loading: until it
// arrives, a chosen model reads as "not suggested" whatever it really is. Quiet
// callers wait that out rather than flash a warning that a suggested model then
// removes, which would shift the rows under it. Non-quiet callers are
// unaffected — they render in every state anyway.
export function show_suggested_advisory(
  model_selected: boolean,
  model_is_suggested: boolean,
  quiet_suggested: boolean,
  suggestion_known: boolean,
): boolean {
  if (quiet_suggested && model_selected && !suggestion_known) {
    return false
  }
  return !(quiet_suggested && model_selected && model_is_suggested)
}
