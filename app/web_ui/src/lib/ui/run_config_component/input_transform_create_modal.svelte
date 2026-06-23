<script lang="ts">
  import Dialog from "$lib/ui/dialog.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import type { InputTransform } from "$lib/types"
  import { buildJinjaInputTransform } from "$lib/utils/run_config_formatters"
  import { client } from "$lib/api_client"
  import { createKilnError } from "$lib/utils/error_handlers"

  export let on_created: (transform: InputTransform) => void

  let dialog: Dialog
  let template_draft = ""
  let validation_error: string | null = null
  let submitting = false

  export function show(initial_template: string = "") {
    template_draft = initial_template
    validation_error = null
    submitting = false
    dialog?.show()
  }

  async function handle_create() {
    validation_error = null
    try {
      const t = template_draft
      if (t.trim().length === 0) {
        validation_error = "Template can't be empty"
        return
      }
      const { data, error } = await client.POST(
        "/api/validate_input_transform_template",
        { body: { template: t } },
      )
      if (error) throw error
      if (!data.valid) {
        validation_error = data.error || "Invalid template"
        return
      }
      on_created(buildJinjaInputTransform(t))
      dialog?.close()
    } catch (e) {
      validation_error =
        createKilnError(e).getMessage() || "Could not validate template"
    } finally {
      submitting = false
    }
  }
</script>

<Dialog
  bind:this={dialog}
  title="Input Transform"
  subtitle="Add a jinja template to transform input"
  sub_subtitle="Learn more about input templates"
  sub_subtitle_link="https://docs.kiln.tech/docs/input-templates-and-feature-engineering"
>
  <FormContainer
    submit_label="Create"
    on:submit={handle_create}
    gap={4}
    bind:submitting
    keyboard_submit={false}
  >
    <textarea
      aria-label="Jinja2 template"
      placeholder="Enter your Jinja2 template..."
      class="textarea textarea-bordered w-full font-mono h-40 text-base whitespace-pre-wrap break-words text-left align-top"
      bind:value={template_draft}
      on:input={() => {
        validation_error = null
      }}
    />
    {#if validation_error}
      <div class="text-error text-sm">{validation_error}</div>
    {/if}
  </FormContainer>
</Dialog>
