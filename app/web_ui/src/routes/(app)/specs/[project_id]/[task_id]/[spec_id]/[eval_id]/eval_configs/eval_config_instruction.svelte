<script lang="ts">
  import type { EvalConfig } from "$lib/types"

  export let eval_config: EvalConfig | null = null

  function get_eval_steps(eval_config: EvalConfig): string[] | undefined {
    if (!eval_config) return undefined
    if (!eval_config.properties) return undefined
    const props = eval_config.properties as Record<string, unknown>
    if (!props["eval_steps"]) return undefined
    if (!Array.isArray(props["eval_steps"])) return undefined
    return props["eval_steps"] as string[]
  }

  function get_task_description(eval_config: EvalConfig): string {
    if (!eval_config?.properties) return "No description provided."
    const props = eval_config.properties as Record<string, unknown>
    return (props["task_description"] as string) || "No description provided."
  }
</script>

{#if eval_config}
  {@const eval_steps = get_eval_steps(eval_config)}
  <div class="text-sm mb-4">
    <div class="font-medium mb-2">Task Description:</div>
    {get_task_description(eval_config)}
  </div>
  {#if eval_steps}
    <div class="text-sm">
      <div class="font-medium mb-2">Evaluation Steps:</div>
      <ol class="list-decimal pl-5">
        {#each eval_steps as step}
          <li>
            <span class="whitespace-pre-line">
              {step}
            </span>
          </li>
        {/each}
      </ol>
    </div>
  {/if}
{/if}
