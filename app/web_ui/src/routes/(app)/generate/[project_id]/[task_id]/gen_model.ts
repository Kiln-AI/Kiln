import type { TaskRunOutput } from "$lib/types"

export type SampleData = {
  input: string
  output: TaskRunOutput | null
  saved_id: string | null
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
