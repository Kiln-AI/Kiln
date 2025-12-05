<script lang="ts">
  import type { EvalConfig } from "$lib/types"

  export let eval_config: EvalConfig | null = null

  // Function to fix type errors
  function get_eval_steps(eval_config: EvalConfig): string[] | undefined {
    if (!eval_config) return undefined
    if (!eval_config.properties) return undefined
    if (!eval_config.properties["eval_steps"]) return undefined
    if (!Array.isArray(eval_config.properties["eval_steps"])) return undefined
    return eval_config.properties["eval_steps"] as string[]
  }
</script>

{#if eval_config}
  {@const eval_steps = get_eval_steps(eval_config)}
  <div class="text-sm mb-4">
    <div class="font-medium mb-2">Task Description:</div>
    {eval_config.properties["task_description"] || "No description provided."}
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
