<script lang="ts">
  // The pilot stop on the review start screen (Pilot First): only the pilot
  // ran. The eval check panel below shows what it says; Continue runs the
  // rest and keeps these results, Refine Plan goes back to the plan.
  import Warning from "$lib/ui/warning.svelte"

  export let ran: number
  export let rest: number
  export let noun: string = "conversation"
  export let on_continue: () => void
  export let on_refine_plan: () => void
</script>

<div class="flex flex-col gap-3" data-pilot-stop>
  <Warning
    warning_color="primary"
    warning_icon="info"
    warning_message={`Pilot: ${ran} ${noun}${ran === 1 ? "" : "s"} ran, spread over the plan. The check below is for these only. Continue sets up and runs the other ${rest} and keeps these results. Refine Plan goes back to the plan.`}
  />
  <div class="flex gap-2 justify-end">
    <button class="btn" on:click={on_refine_plan} data-pilot-refine>
      Refine Plan
    </button>
    <button class="btn btn-primary" on:click={on_continue} data-pilot-continue>
      Continue
    </button>
  </div>
</div>
