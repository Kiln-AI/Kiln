<script lang="ts">
  import CreateSpecForm from "./create_spec_form.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import ToolsSelector from "$lib/ui/run_config_component/tools_selector.svelte"
  import { page } from "$app/stores"

  $: project_id = $page.params.project_id
  $: task_id = $page.params.task_id
  let selected_tool: string | null = null
  let appropriate_tool_use_guidelines = ""
  let inappropriate_tool_use_guidelines = ""
</script>

<CreateSpecForm
  spec_type="appropriate_tool_use"
  form_has_unsaved_changes={!!(
    selected_tool ||
    appropriate_tool_use_guidelines ||
    inappropriate_tool_use_guidelines
  )}
  get_properties={() => ({
    spec_type: "appropriate_tool_use",
    tool_id: selected_tool ?? "",
    appropriate_tool_use_guidelines: appropriate_tool_use_guidelines,
    inappropriate_tool_use_guidelines: inappropriate_tool_use_guidelines,
  })}
>
  <svelte:fragment slot="form_elements">
    <ToolsSelector
      {project_id}
      {task_id}
      label="Tool to Evaluate"
      description="Select the tool you want to evaluate for appropriate use."
      info_description={undefined}
      single_select={true}
      bind:single_select_selected_tool={selected_tool}
    />
    <FormElement
      label="Appropriate Tool Use Guidelines"
      description="Guidelines or examples of when the tool should be used. This will be used by AI to understand the spec."
      info_description="Include guidelines or examples to help the judge model understand when the tool should be used. The format is flexible (plain text). You can include a description or multiple examples if needed."
      inputType="textarea"
      id="should_call_example"
      bind:value={appropriate_tool_use_guidelines}
    />
    <FormElement
      label="Inappropriate Tool Use Guidelines"
      description="Guidelines or examples of when the tool should not be used. This will be used by AI to understand the spec."
      info_description="Include guidelines or examples to help the judge model understand when the tool should not be used. The format is flexible (plain text). You can include a description or multiple examples if needed."
      inputType="textarea"
      id="should_not_call_example"
      optional={true}
      bind:value={inappropriate_tool_use_guidelines}
    />
  </svelte:fragment>
</CreateSpecForm>
