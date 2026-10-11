import type { TaskRunOutput } from "$lib/types"

export type SampleData = {
  input: string
  output: TaskRunOutput | null
  saved_id: string | null
  // Set instead of saved_id when the case was saved to the eval's inputs rather than run
  // and saved as a run.
  eval_input_id?: string | null
  // The split this case was dealt, drawn once when it is generated. A case on a split that
  // holds eval inputs has no output, so its split is the only thing saying where it goes.
  split_tag?: string | null
  model_name: string
  model_provider: string
  // Optional. The tree path to the topic that the sample belongs to.
  // The actual node tree has this, but it can also be stored here for convenience.
  topic_path?: string[]
}

export type SampleDataNode = {
  topic: string
  sub_topics: SampleDataNode[]
  samples: SampleData[]
}
