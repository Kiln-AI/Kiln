<script lang="ts">
  // The planned conversations grounding dropped, each with its reason. The
  // first few show; the rest wait behind a Collapse, so a long list doesn't
  // push the actions below it out of view.
  import ClampedText from "$lib/ui/clamped_text.svelte"
  import Collapse from "$lib/ui/collapse.svelte"
  import SeeAllDialog from "$lib/ui/see_all_dialog.svelte"
  import type { GroundingDrop } from "./grounding_flow"

  export let drops: GroundingDrop[]

  const VISIBLE_ROWS = 5

  let see_all_dialog: SeeAllDialog

  $: shown = drops.slice(0, VISIBLE_ROWS)
  $: hidden = drops.slice(VISIBLE_ROWS)

  function see_all(scenario: string) {
    see_all_dialog.show("Dropped Conversation", scenario)
  }
</script>

<div class="flex flex-col gap-4 w-full">
  <div class="rounded-lg border">
    <table class="table">
      <thead>
        <tr>
          <th>Dropped Conversations</th>
        </tr>
      </thead>
      <tbody>
        {#each shown as drop}
          <tr data-dropped-case>
            <td class="max-w-0">
              <ClampedText
                content={drop.scenario}
                max_lines={1}
                text_class="font-sans whitespace-pre-wrap break-words text-sm"
                on:see_all={() => see_all(drop.scenario)}
              />
              <div class="text-sm text-gray-500 mt-1">{drop.drop_detail}</div>
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
  {#if hidden.length > 0}
    <Collapse title={`${hidden.length} More`}>
      <div class="rounded-lg border">
        <table class="table">
          <tbody>
            {#each hidden as drop}
              <tr data-dropped-case>
                <td class="max-w-0">
                  <ClampedText
                    content={drop.scenario}
                    max_lines={1}
                    text_class="font-sans whitespace-pre-wrap break-words text-sm"
                    on:see_all={() => see_all(drop.scenario)}
                  />
                  <div class="text-sm text-gray-500 mt-1">
                    {drop.drop_detail}
                  </div>
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    </Collapse>
  {/if}
</div>

<SeeAllDialog bind:this={see_all_dialog} />
