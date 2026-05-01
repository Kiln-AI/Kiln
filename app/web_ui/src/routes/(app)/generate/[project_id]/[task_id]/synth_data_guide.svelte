<script lang="ts">
  import Dialog from "$lib/ui/dialog.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import Output from "$lib/ui/output.svelte"
  import { SynthDataGuidanceDataModel } from "./synth_data_guidance_datamodel"

  export let guidance_data: SynthDataGuidanceDataModel

  let view_dialog: Dialog | null = null

  // Read the canonical saved guide text from the datamodel (kept in sync by
  // the synth page on load) rather than taking it as a prop, so every place
  // that renders this component sees the same value.
  let saved_guide_text_store = guidance_data.saved_guide_text
  let data_guide_store = guidance_data.data_guide

  // Toggle reflects whether the per-run data_guide override is non-empty —
  // i.e. whether the saved guide will be sent with this generation.
  $: enabled = !!$data_guide_store?.trim()

  // Keep `enabled` in sync with the FormElement's bound boolean and propagate
  // changes to the per-run override store.
  function set_enabled(next: boolean) {
    if (next === enabled) return
    guidance_data.data_guide.set(next ? $saved_guide_text_store : "")
  }
  $: set_enabled(enabled_value)

  // Local boolean bound to the FormElement checkbox; we mirror it into the
  // store via the reactive above. Initialized from the current store state.
  let enabled_value: boolean = enabled
  $: enabled_value = enabled

  function show_view_dialog() {
    view_dialog?.show()
  }
</script>

<div class="flex flex-col gap-1">
  <FormElement
    id="data_guide_toggle"
    label="Use Data Guide"
    description="Guidelines, and rules for task data to follow, with examples."
    inputType="checkbox"
    bind:value={enabled_value}
    disabled={!$saved_guide_text_store}
    inline_action={$saved_guide_text_store
      ? {
          handler: show_view_dialog,
          label: "View",
        }
      : null}
  />
</div>

<Dialog bind:this={view_dialog} title="Data Guide" width="wide">
  <Output raw_output={$saved_guide_text_store} />
</Dialog>
