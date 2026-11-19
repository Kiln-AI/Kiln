<script lang="ts">
  // The screen after grounding when some planned cases couldn't be made to
  // fit the OpenEnv server. It names each one with the grounding agent's own
  // reason and offers the ways on: drive the cases that fit, plan the batch
  // again with these reasons in hand, plan new cases for only these rows, or
  // go back to the plan.
  import SettingsHeader from "$lib/ui/settings_header.svelte"
  import ClampedText from "$lib/ui/clamped_text.svelte"
  import SeeAllDialog from "$lib/ui/see_all_dialog.svelte"
  import Warning from "$lib/ui/warning.svelte"
  import type { GroundingDrop } from "./grounding_flow"

  export let drops: GroundingDrop[]
  // How many cases were checked: the fitting ones plus the drops.
  export let total: number
  export let on_cancel: () => void
  export let on_retry: () => void
  export let on_replace: () => void
  export let on_continue: () => void
  // Why the last Replace Dropped Cases stopped part-way, when it failed.
  export let error: string | null = null

  let see_all_dialog: SeeAllDialog

  $: fit_count = Math.max(0, total - drops.length)
  $: summary =
    fit_count === 0
      ? `Kiln checked each case against your OpenEnv server. None of the ${total} cases could be made to fit.`
      : `Kiln checked each case against your OpenEnv server. ${drops.length} of ${total} couldn't be made to fit.`
</script>

<div class="flex flex-col gap-6">
  <SettingsHeader
    title="Some Cases Don't Fit Your Environment"
    subtitle={summary}
  />
  <div class="rounded-lg border">
    <table class="table">
      <thead>
        <tr>
          <th>Dropped Cases</th>
        </tr>
      </thead>
      <tbody>
        {#each drops as drop}
          <tr data-dropped-case>
            <td class="max-w-0">
              <ClampedText
                content={drop.scenario}
                max_lines={1}
                text_class="font-sans whitespace-pre-wrap break-words text-sm"
                on:see_all={() =>
                  see_all_dialog.show("Dropped Case", drop.scenario)}
              />
              <div class="text-sm text-gray-500 mt-1">{drop.drop_detail}</div>
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
  {#if error}
    <Warning warning_color="error" warning_message={error} />
  {/if}
  <!-- Right-aligned, primary last. With nothing left to drive, Continue and
       Replace go (there are no kept cases to plan around), and Retry is the
       way forward. -->
  <div class="flex justify-end gap-2">
    <button class="btn" on:click={on_cancel}>Cancel</button>
    <button
      class="btn {fit_count === 0 ? 'btn-primary' : ''}"
      on:click={on_retry}
    >
      Retry
    </button>
    {#if fit_count > 0}
      <button class="btn" on:click={on_replace}>Replace Dropped Cases</button>
      <button class="btn btn-primary" on:click={on_continue}>
        Continue With {fit_count}
      </button>
    {/if}
  </div>
</div>

<SeeAllDialog bind:this={see_all_dialog} />
