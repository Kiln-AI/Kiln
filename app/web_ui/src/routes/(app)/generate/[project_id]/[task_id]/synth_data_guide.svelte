<script lang="ts">
  import Dialog from "$lib/ui/dialog.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import { SynthDataGuidanceDataModel } from "./synth_data_guidance_datamodel"
  import { onDestroy } from "svelte"
  import { writable } from "svelte/store"

  export let guidance_data: SynthDataGuidanceDataModel

  let data_guide_dialog: Dialog | null = null

  let data_guide_store = guidance_data.data_guide
  // Disconnect our local reference so the bind: doesn't reset the store on destroy
  onDestroy(() => {
    data_guide_store = writable("")
  })

  function show_data_guide_dialog() {
    data_guide_dialog?.show()
  }

  function clear_data_guide() {
    guidance_data.data_guide.set("")
    return false
  }

  $: button_label = $data_guide_store?.trim()
    ? `${$data_guide_store.length} characters`
    : "None"
</script>

<div class="flex flex-col">
  <FormElement
    id="data_guide_header"
    label="Data Guide"
    description="A reference document that describes the structure, rules, and examples for task data."
    info_description="The data guide is included with every generation request to anchor synthetic data on real-world structure and constraints. Edits here apply to this run only and are not saved back to the task."
    inputType="header_only"
    value={null}
  />
  <button
    class="select select-bordered w-full flex items-center"
    on:click={show_data_guide_dialog}
    tabindex="0"
    type="button"
  >
    {button_label}
  </button>
</div>

<Dialog
  bind:this={data_guide_dialog}
  title="Data Guide"
  width="wide"
  action_buttons={[
    {
      label: "Clear",
      action: clear_data_guide,
      disabled: !$data_guide_store,
    },
    {
      label: "Done",
      isPrimary: true,
    },
  ]}
>
  <div>
    <div class="text-sm text-gray-500">
      Edit the data guide that will be sent with this generation request. Edits
      apply only to this run and are not saved back to the task.
    </div>

    <div class="flex flex-col gap-2 w-full mt-4">
      <FormElement
        id="data_guide_text"
        label="Data Guide"
        description="The data guide content (markdown)."
        inputType="textarea"
        optional={true}
        height="xl"
        bind:value={$data_guide_store}
      />
    </div>
  </div>
</Dialog>
