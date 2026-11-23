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

  export let on_start: () => void
  export let judged_noun: string = "example"
  // When checking the plan against an OpenEnv server dropped some of it: a
  // warning under the description, Start becomes Continue, and Refine Plan
  // is offered beside it.
  export let drops_warning: string | null = null
  export let on_refine_plan: () => void = () => {}
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
    action_buttons={drops_warning
      ? [
          { label: "Continue", onClick: on_start, is_primary: true },
          { label: "Refine Plan", onClick: on_refine_plan, is_primary: false },
        ]
      : [{ label: "Start", onClick: on_start, is_primary: true }]}
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
