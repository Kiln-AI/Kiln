<script lang="ts">
  // PREVIEW (09-02): Step 5's entry screen. Reviewers arrived straight into
  // a stack of grading with no statement of why they were doing it. This
  // says what the step is for once, and gets out of the way.
  //
  // Uses the shared Intro control (the app's empty/entry screen), so this
  // screen inherits the same width, type scale, icon size and button
  // treatment as every other one rather than restating them here.
  //
  // Wording is the reviewer's, unchanged. The one break he wrote as a newline
  // is two paragraphs because that is how this control expresses one. The
  // noun is the only substitution: he wrote "examples", which is wrong on the
  // multi-turn arm where every item is a conversation.
  import Intro from "$lib/ui/intro.svelte"
  import Warning from "$lib/ui/warning.svelte"
  import ScalesIcon from "$lib/ui/icons/scales_icon.svelte"
  import type { DropsAction } from "./grounding_flow"

  export let on_start: () => void
  export let judged_noun: string = "example"
  // When checking the plan against an OpenEnv server dropped some of it: a
  // warning under the description, and Start gives way to Continue and Refine
  // Plan. `drops_action` says which leads (see drops_action in
  // grounding_flow.ts); `kept_count` is how many items Continue keeps. A
  // refine_only batch never reaches this screen: drops_refine_screen takes
  // its place.
  export let drops_warning: string | null = null
  export let drops_action: DropsAction = "continue_first"
  export let kept_count: number = 0
  export let on_refine_plan: () => void = () => {}

  type IntroButton = { label: string; onClick: () => void; is_primary: boolean }

  function buttons(
    warning: string | null,
    action: DropsAction,
    kept: number,
  ): IntroButton[] {
    if (!warning)
      return [{ label: "Start", onClick: on_start, is_primary: true }]
    const refine = { label: "Refine Plan", onClick: on_refine_plan }
    if (action === "refine_first") {
      return [
        { ...refine, is_primary: true },
        {
          label: `Continue with ${kept}`,
          onClick: on_start,
          is_primary: false,
        },
      ]
    }
    return [
      { label: "Continue", onClick: on_start, is_primary: true },
      { ...refine, is_primary: false },
    ]
  }
</script>

<!-- Centred with flex rather than mx-auto: the step body is a full-width
     block here, so mx-auto on the wrapper has nothing to centre against and
     Intro's own 300px column would sit against the left edge. -->
<div class="flex justify-center mt-[10vh]">
  <Intro
    title="Align the Judge"
    description_paragraphs={[
      "Let's confirm your judge is aligned to your expectations.",
      `We'll show a set of ${judged_noun}s, and you tell us if you agree with its judgement.`,
    ]}
    action_buttons={buttons(drops_warning, drops_action, kept_count)}
  >
    <div slot="icon" class="h-12 w-12">
      <ScalesIcon />
    </div>
    <div slot="description">
      {#if drops_warning}
        <Warning warning_color="warning" warning_message={drops_warning} />
      {/if}
    </div>
  </Intro>
</div>
