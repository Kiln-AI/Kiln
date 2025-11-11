<script lang="ts">
  import Dialog from "$lib/ui/dialog.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import { DEFAULT_QNA_GUIDANCE } from "./guidance"
  import type { OptionGroup } from "$lib/ui/fancy_select_types"

  export let guidance: string = ""
  export let selected_template: string = "custom"

  let guidance_dialog: Dialog | null = null
  let last_selected_template: string = "custom"

  const select_options: OptionGroup[] = [
    {
      label: "Built-in Templates",
      options: [
        {
          label: "Q&A Generation",
          value: "query_answer_generation",
          description: "Generate Q&A pairs for the selected documents",
        },
      ],
    },
    {
      label: "Custom Guidance",
      options: [
        {
          label: "Custom",
          value: "custom",
          description: "Enter your own guidance",
        },
      ],
    },
  ]

  $: {
    if (
      selected_template === "query_answer_generation" &&
      last_selected_template !== "query_answer_generation"
    ) {
      guidance = DEFAULT_QNA_GUIDANCE
      last_selected_template = "query_answer_generation"
    } else if (selected_template === "custom") {
      if (last_selected_template !== "custom") {
        guidance = ""
        last_selected_template = "custom"
      }
    }
  }

  function show_guidance_dialog() {
    guidance_dialog?.show()
  }

  function clear_guidance() {
    guidance = ""
    selected_template = "custom"
    last_selected_template = "custom"
    return false
  }

  function get_guidance_label(
    guidance: string,
    selected_template: string,
  ): string {
    if (!guidance) {
      return "None"
    }

    if (selected_template === "query_answer_generation") {
      return "Q&A Generation Template"
    } else if (selected_template === "custom") {
      return "Custom Template"
    }
    return "None"
  }
</script>

<div class="flex flex-col">
  <FormElement
    id="guidance_type"
    label="Guidance"
    description="Instructions to steer query-answer pair generation."
    info_description="Special instructions/prompt to help the model generate relevant Q&A pairs. You can use the default QA guidance or create custom guidance."
    inputType={"header_only"}
    value={null}
  />
  <button
    class="select select-bordered w-full flex items-center"
    on:click={show_guidance_dialog}
    tabindex="0"
  >
    {get_guidance_label(guidance, selected_template)}
  </button>
</div>

<Dialog
  bind:this={guidance_dialog}
  title="Guidance for Q&A Generation"
  sub_subtitle="Add guidance to steer the AI-generated Q&A pairs."
  width="wide"
  action_buttons={[
    {
      label: "Clear",
      action: clear_guidance,
      disabled: !guidance,
    },
    {
      label: "Done",
      isPrimary: true,
    },
  ]}
>
  <div>
    <div class="flex flex-col gap-2 w-full mt-4">
      <FormElement
        id="template_id"
        label="Templates"
        inputType={"fancy_select"}
        fancy_select_options={select_options}
        bind:value={selected_template}
      />
      <FormElement
        id="guidance"
        label="Guidance"
        description="Guidance to help the model generate relevant Q&A pairs."
        inputType={"textarea"}
        optional={true}
        height="large"
        bind:value={guidance}
      />
    </div>
  </div>
</Dialog>
