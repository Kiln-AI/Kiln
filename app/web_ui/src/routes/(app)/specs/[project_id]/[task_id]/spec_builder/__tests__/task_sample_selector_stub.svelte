<script lang="ts">
  // Stand-in for task_sample_selector. Mirrors its props so binding parents
  // render without warnings, but does no API work.
  import type { TaskSampleExample } from "$lib/utils/task_sample_example"

  export let project_id: string = ""
  export let task_id: string = ""
  export let selected_example: TaskSampleExample | null = null
  export let is_prompt_building: boolean = false
  export let has_unsaved_manual_entry: boolean = false

  // Referenced so the unused-export lint stays quiet for props we only accept.
  void project_id
  void task_id
  void selected_example
  void is_prompt_building
  void has_unsaved_manual_entry
</script>

<div data-testid="task-sample-selector-stub">task sample selector stub</div>
