<script lang="ts">
  import FormElement from "$lib/utils/form_element.svelte"
  import { SynthDataGuidanceDataModel } from "./synth_data_guidance_datamodel"

  export let guidance_data: SynthDataGuidanceDataModel

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

  function open_data_guide_in_new_tab() {
    const project_id = guidance_data.project_id
    const task_id = guidance_data.task_id
    if (!project_id || !task_id) return
    window.open(
      `/generate/${project_id}/${task_id}/data_guide`,
      "_blank",
      "noopener,noreferrer",
    )
  }
</script>

<div class="flex flex-col gap-1">
  <FormElement
    id="data_guide_toggle"
    label="Use Data Guide"
    inputType="checkbox"
    bind:value={enabled_value}
    disabled={!$saved_guide_text_store}
    inline_action={$saved_guide_text_store
      ? {
          handler: open_data_guide_in_new_tab,
          label: "View",
        }
      : null}
  />
</div>
