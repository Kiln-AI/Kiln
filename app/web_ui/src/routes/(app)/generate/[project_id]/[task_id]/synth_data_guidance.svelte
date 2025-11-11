<script lang="ts">
  import Dialog from "$lib/ui/dialog.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import Warning from "$lib/ui/warning.svelte"
  import { SynthDataGuidanceDataModel } from "./synth_data_guidance_datamodel"
  import { onDestroy } from "svelte"
  import { writable } from "svelte/store"

  type GuidanceType = "topics" | "inputs" | "outputs"
  export let guidance_type: GuidanceType

  export let guidance_data: SynthDataGuidanceDataModel

  let guidance_dialog: Dialog | null = null

  // Local reference to the store needed for svelte syntax
  let selected_template_store = guidance_data.selected_template
  let guidance_store = guidance_data.guidance_store_for_type(guidance_type)
  const select_options_store = guidance_data.select_options
  // Disconnect our local reference from the store when the component is destroyed or else the bind: below will set them to undefined
  onDestroy(() => {
    selected_template_store = writable("")
    guidance_store = writable("")
  })

  function clear_guidance() {
    guidance_data.set_guidance_for_type(guidance_type, null, "custom")
    return false
  }

  function show_guidance_dialog() {
    guidance_dialog?.show()
  }

  type GuidanceStrings = {
    title: string
    description: string
    description_plural: string
  }
  const guidance_type_strings: Record<GuidanceType, GuidanceStrings> = {
    topics: {
      title: "Guidance for Topic Generation",
      description: "topic",
      description_plural: "topics",
    },
    inputs: {
      title: "Guidance for Input Generation",
      description: "task input",
      description_plural: "task inputs",
    },
    outputs: {
      title: "Guidance for Output Generation",
      description: "task output",
      description_plural: "task outputs",
    },
  }

  function title(): string {
    return guidance_type_strings[guidance_type].title
  }

  function description(): string {
    return guidance_type_strings[guidance_type].description
  }

  function description_plural(): string {
    return guidance_type_strings[guidance_type].description_plural
  }
</script>

<div class="flex flex-col">
  <FormElement
    id="guidance_type"
    label="Guidance"
    description={`Instructions to steer the ${description()} generation.`}
    info_description={`Special instructions/prompt to help the model generate relevant ${description_plural()}. For example, for a Bias Eval you might ask for sensitive topics. We'll attempt to select a appropriate template for you, but you may edit it or create custom guidance.`}
    inputType={"header_only"}
    value={null}
  />
  <button
    class="select select-bordered w-full flex items-center"
    on:click={show_guidance_dialog}
    tabindex="0"
  >
    {guidance_data.guidance_label($selected_template_store, $guidance_store)}
  </button>
</div>

<Dialog
  bind:this={guidance_dialog}
  title={title()}
  width="wide"
  action_buttons={[
    {
      label: "Clear",
      action: clear_guidance,
      disabled: !$guidance_store,
    },
    {
      label: "Done",
      isPrimary: true,
    },
  ]}
>
  <div>
    <div class="text-sm text-gray-500">
      Add guidance to improve or steer the AI-generated {description_plural()}.
      Learn more and see examples
      <a
        href="https://docs.kiln.tech/docs/synthetic-data-generation#human-guidance"
        target="_blank"
        class="link">in the docs</a
      >.
    </div>

    <div class="flex flex-col gap-2 w-full mt-4">
      <FormElement
        id="template_id"
        label="Templates"
        inputType={"fancy_select"}
        fancy_select_options={$select_options_store}
        bind:value={$selected_template_store}
      />
      <FormElement
        id="guidance"
        label="Guidance"
        description={`Guidance to help the model generate relevant ${description_plural()}.`}
        inputType={"textarea"}
        optional={true}
        height="large"
        bind:value={$guidance_store}
      />
      {#if guidance_data.custom_warning($selected_template_store)}
        <div class="flex flex-row gap-2">
          <Warning
            large_icon={true}
            warning_color="warning"
            warning_message={guidance_data.custom_warning(
              $selected_template_store,
            )}
          />
        </div>
      {/if}
    </div>
  </div>
</Dialog>
