<script lang="ts">
  import FormElement from "$lib/utils/form_element.svelte"
  import type { Task, TaskRun } from "$lib/types"
  import FormContainer from "../../../lib/utils/form_container.svelte"

  export let on_submit: (run: TaskRun) => void
  export let on_cancel: () => void

  export let task: Task
  export let repair_run: TaskRun

  function validate_output(text: string) {
    if (task.output_json_schema) {
      try {
        // TODO: validate against the JSON schema instead of just checking if it is valid JSON
        JSON.parse(text)
        return true
      } catch (err) {
        return false
      }
    }

    return true
  }

  function prettify_output(text: string) {
    if (task.output_json_schema) {
      try {
        return JSON.stringify(JSON.parse(text), null, 2)
      } catch (err) {
        return text
      }
    }
    return text
  }

  $: repair_output_edited_valid = validate_output(repair_output_edited)
  let repair_output_edited = prettify_output(repair_run.output.output) || ""

  function handle_submit() {
    const human_edited_run: TaskRun = {
      ...repair_run,
      output: {
        ...repair_run.output,
        output: repair_output_edited,
        source: {
          type: "human",
          properties: {
            // the user name will be replaced with the actual user name on the server side
            created_by: "user",
          },
        },
      },
    }
    on_submit(human_edited_run)
  }

  function handle_cancel() {
    on_cancel()
  }
</script>

<div>
  {#if task.output_json_schema}
    {#if repair_output_edited_valid}
      <div class="text-xs font-medium text-gray-500 flex flex-row mb-2">
        <svg
          fill="currentColor"
          class="w-4 h-4 mr-[2px]"
          viewBox="0 0 56 56"
          xmlns="http://www.w3.org/2000/svg"
          ><path
            d="M 27.9999 51.9063 C 41.0546 51.9063 51.9063 41.0781 51.9063 28 C 51.9063 14.9453 41.0312 4.0937 27.9765 4.0937 C 14.8983 4.0937 4.0937 14.9453 4.0937 28 C 4.0937 41.0781 14.9218 51.9063 27.9999 51.9063 Z M 24.7655 40.0234 C 23.9687 40.0234 23.3593 39.6719 22.6796 38.8750 L 15.9296 30.5312 C 15.5780 30.0859 15.3671 29.5234 15.3671 29.0078 C 15.3671 27.9063 16.2343 27.0625 17.2655 27.0625 C 17.9452 27.0625 18.5077 27.3203 19.0702 28.0469 L 24.6718 35.2890 L 35.5702 17.8281 C 36.0155 17.1016 36.6249 16.75 37.2343 16.75 C 38.2655 16.75 39.2733 17.4297 39.2733 18.5547 C 39.2733 19.0703 38.9687 19.6328 38.6640 20.1016 L 26.7577 38.8750 C 26.2421 39.6484 25.5858 40.0234 24.7655 40.0234 Z"
          /></svg
        >
        Structure Valid
      </div>
    {:else}
      <div
        class="text-xs font-medium text-error flex flex-row mb-2 items-center"
      >
        <svg
          class="w-4 h-4 mr-[2px] text-error"
          fill="currentColor"
          viewBox="0 0 256 256"
          id="Flat"
          xmlns="http://www.w3.org/2000/svg"
        >
          <path
            d="M128,20.00012a108,108,0,1,0,108,108A108.12217,108.12217,0,0,0,128,20.00012Zm0,192a84,84,0,1,1,84-84A84.0953,84.0953,0,0,1,128,212.00012Zm-12-80v-52a12,12,0,1,1,24,0v52a12,12,0,1,1-24,0Zm28,40a16,16,0,1,1-16-16A16.018,16.018,0,0,1,144,172.00012Z"
          />
        </svg>
        Structure does not match required schema
      </div>
    {/if}
  {/if}

  <FormContainer
    submit_label="Apply"
    on:submit={handle_submit}
    disabled={!repair_output_edited_valid}
  >
    <FormElement
      id={"repair_manual_output"}
      label="Manual Repair"
      inputType="textarea"
      tall={true}
      bind:value={repair_output_edited}
    />

    <button
      class="link text-gray-500 text-sm text-right"
      on:click={handle_cancel}>Cancel edit</button
    >
  </FormContainer>
</div>
