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
