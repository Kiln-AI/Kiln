<script lang="ts">
  // Feedback the refine declined, said out loud over the round it produced —
  // a note silently dropped reads as ignored. One item per conversation it
  // names, each opening with the conversation's first message so the reviewer
  // can place it; the subset is redrawn each round, so a position or an id
  // would point at nothing.
  import Warning from "$lib/ui/warning.svelte"
  import { DECLINED_FEEDBACK_HEADING } from "./claim_evidence"

  export let items: string[]
</script>

<div class="flex flex-col gap-2">
  <Warning
    warning_color="primary"
    warning_icon="info"
    warning_message={DECLINED_FEEDBACK_HEADING}
  />
  <ul
    id="declined_feedback_items"
    class="list-disc pl-10 text-sm font-light text-gray-500 flex flex-col gap-1"
  >
    {#each items as item}
      <li>{item}</li>
    {/each}
  </ul>
</div>
