<script lang="ts">
  import { createEventDispatcher } from "svelte"

  export let name: string = ""
  export let priority: number = 1
  export let judge_type: string
  export let project_id: string
  export let task_id: string
  export let error: unknown = null
  export let submitting: boolean = false
  export let warn_before_unload: boolean = false

  export function validateJudge(): string | null {
    return null
  }

  export function getJudgeProperties(): Record<string, unknown> {
    return { type: judge_type }
  }

  const dispatch = createEventDispatcher()
</script>

<button
  data-testid="judge-form-save"
  data-name={name}
  data-priority={priority}
  data-project-id={project_id}
  data-task-id={task_id}
  data-error={String(error)}
  data-submitting={submitting}
  data-warn-before-unload={warn_before_unload}
  on:click={() => dispatch("save")}>Save</button
>
