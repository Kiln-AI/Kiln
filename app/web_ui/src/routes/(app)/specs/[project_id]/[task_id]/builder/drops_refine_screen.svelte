<script lang="ts">
  // The screen that sends a build back to planning: every planned item
  // dropped when Kiln checked it against the OpenEnv server, or so many that
  // what's left can't make a useful eval. No reasons list and no review:
  // Refine Plan plans again with the drops in hand.
  import Intro from "$lib/ui/intro.svelte"
  import ExclaimCircleIcon from "$lib/ui/icons/exclaim_circle_icon.svelte"
  import { drops_refine_text, type PlannedNoun } from "./grounding_flow"

  export let dropped: number
  export let planned: number
  export let noun: PlannedNoun
  export let on_refine_plan: () => void
</script>

<div class="flex justify-center mt-[10vh]">
  <Intro
    title={dropped >= planned
      ? "None of the Plan Fit"
      : "Most of the Plan Didn't Fit"}
    description_paragraphs={[drops_refine_text(dropped, planned, noun)]}
    action_buttons={[
      { label: "Refine Plan", onClick: on_refine_plan, is_primary: true },
    ]}
  >
    <div slot="icon" class="h-12 w-12 text-warning">
      <ExclaimCircleIcon />
    </div>
  </Intro>
</div>
