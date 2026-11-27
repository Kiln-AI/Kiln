<script lang="ts">
  // The pilot stop's first view, inside the generate progress screen: every
  // first message the case writer wrote, before any grounding call. Continue
  // goes on with the build; Refine goes back to the plan with the draft kept.
  import SettingsHeader from "$lib/ui/settings_header.svelte"
  import { first_messages } from "./pilot_flow"

  export let cases: { seed_prompt: string; scenario_index?: number | null }[]
  export let on_continue: () => void
  export let on_refine: () => void

  $: rows = first_messages(cases)
</script>

<div class="flex flex-col gap-4 max-w-4xl mx-auto" data-first-messages-review>
  <SettingsHeader
    title="Read the First Messages"
    subtitle={`The simulated users' ${rows.length} first messages, as written. Nothing has been set up in the environment or run yet. Continue to set up and run the cases, or Refine the plan.`}
  />
  <div class="rounded-lg border max-h-[55vh] overflow-y-auto">
    <ol class="divide-y" data-first-messages>
      {#each rows as row (row.key)}
        <li class="p-4 flex flex-col gap-1">
          <span class="text-xs text-gray-500">{row.label}</span>
          <span class="text-sm whitespace-pre-wrap">{row.text}</span>
        </li>
      {/each}
    </ol>
  </div>
  <div class="flex gap-2 justify-end">
    <button class="btn" on:click={on_refine} data-first-messages-refine>
      Refine
    </button>
    <button
      class="btn btn-primary"
      on:click={on_continue}
      data-first-messages-continue
    >
      Continue
    </button>
  </div>
</div>
