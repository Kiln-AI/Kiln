import type { Writable } from "svelte/store"
import type { Eval, Task, Spec } from "$lib/types"
import { getContext } from "svelte"

export const CREATE_EVAL_LAYOUT_KEY = "create_eval_layout"

export type CreateEvalLayoutContext = {
  evaluator: Writable<Eval | undefined>
  task: Writable<Task | null>
  spec: Writable<Spec | null>
  project_id: Writable<string>
  task_id: Writable<string>
  eval_id: Writable<string>
  spec_id: Writable<string>
}

export function getCreateEvalLayoutContext(): CreateEvalLayoutContext {
  return getContext<CreateEvalLayoutContext>(CREATE_EVAL_LAYOUT_KEY)
}
