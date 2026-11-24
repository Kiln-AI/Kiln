<script lang="ts">
  // A multi-turn task's Data Guide as plain text: one box and Save, which
  // writes the task's guide. Multi-turn tasks skip the single-turn setup and
  // refine pages, because those build and check a guide by generating
  // example inputs, and synthetic data generation is single-turn only. The
  // eval builder opens it to create a guide; the Data Guide page opens it to
  // edit one.
  import Dialog from "$lib/ui/dialog.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import { client } from "$lib/api_client"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import type { DataGuide } from "$lib/types"

  export let project_id: string
  export let task_id: string
  export let title: string = "Data Guide"
  export let on_saved: (saved: DataGuide) => void

  let dialog: Dialog | null = null
  let text = ""
  let submitting = false
  let error: KilnError | null = null

  export function show(initial_text: string = ""): void {
    text = initial_text
    error = null
    dialog?.show()
  }

  async function save(): Promise<void> {
    error = null
    submitting = true
    try {
      const { data, error: api_error } = await client.PUT(
        "/api/projects/{project_id}/tasks/{task_id}/data_gen_guide",
        {
          params: { path: { project_id, task_id } },
          body: { guide: text.trim() },
        },
      )
      if (api_error) throw api_error
      if (!data) throw new KilnError("The Data Guide wasn't saved.")
      dialog?.close()
      on_saved(data)
    } catch (e) {
      error = createKilnError(e)
    } finally {
      submitting = false
    }
  }
</script>

<Dialog bind:this={dialog} {title} width="wide">
  <FormContainer
    submit_label="Save"
    bind:submitting
    {error}
    submit_disabled={text.trim() === ""}
    on:submit={save}
    keyboard_submit={false}
  >
    <FormElement
      label="Guide"
      description="Who talks to your agent, their roles, what each one asks for, and what each one can and can't do."
      id="data_guide_text"
      inputType="textarea"
      height="xl"
      bind:value={text}
    />
  </FormContainer>
</Dialog>
