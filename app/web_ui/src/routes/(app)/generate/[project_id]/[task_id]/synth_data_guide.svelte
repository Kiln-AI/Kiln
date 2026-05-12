<script lang="ts">
  import FormElement from "$lib/utils/form_element.svelte"
  import { SynthDataGuidanceDataModel } from "./synth_data_guidance_datamodel"

  export let guidance_data: SynthDataGuidanceDataModel

  let data_guide_store = guidance_data.data_guide
  let use_data_guide_store = guidance_data.use_data_guide

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

{#if $data_guide_store}
  <div class="flex flex-col gap-1">
    <FormElement
      id="data_guide_toggle"
      label="Use Data Guide"
      inputType="checkbox"
      bind:value={$use_data_guide_store}
      inline_action={{
        handler: open_data_guide_in_new_tab,
        label: "View",
      }}
    />
  </div>
{/if}
