<script lang="ts">
  import { createEventDispatcher } from "svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import { client } from "$lib/api_client"
  import { createKilnError, KilnError } from "$lib/utils/error_handlers"
  import { string_to_json_key } from "$lib/utils/json_schema_editor/json_schema_templates"
  import { score_display_name } from "$lib/utils/formatters"
  import type { EvalOutputScore } from "$lib/types"

  export let project_id: string
  export let task_id: string

  const dispatch = createEventDispatcher<{
    saved: { eval_id: string; score_key: string; display_name: string }
  }>()

  let dialog: Dialog | null = null
  let eval_id: string | null = null
  let score_key: string | null = null
  let score: EvalOutputScore | null = null
  let display_name = ""
  let loading = false
  let error: KilnError | null = null
  let submitting = false
  // Each show() bumps this; a response from an earlier opening is ignored.
  let load_id = 0

  export async function show(target_eval_id: string, target_score_key: string) {
    const this_load_id = ++load_id
    eval_id = target_eval_id
    score_key = target_score_key
    score = null
    display_name = ""
    error = null
    dialog?.show()

    loading = true
    try {
      const { data, error: get_error } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}",
        { params: { path: { project_id, task_id, eval_id: target_eval_id } } },
      )
      if (this_load_id !== load_id) {
        return
      }
      if (get_error) {
        throw get_error
      }
      score =
        data.output_scores.find(
          (s) => string_to_json_key(s.name) === target_score_key,
        ) || null
      if (!score) {
        throw new Error("This score no longer exists on the eval.")
      }
      display_name = score_display_name(score)
    } catch (e) {
      if (this_load_id === load_id) {
        error = createKilnError(e)
      }
    } finally {
      if (this_load_id === load_id) {
        loading = false
      }
    }
  }

  const max_length = 32

  // Replaces FormElement's default check, which treats whitespace-only as filled in.
  function validate_display_name(value: unknown): string | null {
    if (typeof value !== "string" || value.trim().length === 0) {
      return "Score name is required."
    }
    if (value.length > max_length) {
      return `Score name is too long. Max length is ${max_length} characters.`
    }
    return null
  }

  async function save() {
    if (!eval_id || !score_key) {
      return
    }
    const validation_error = validate_display_name(display_name)
    if (validation_error) {
      throw new Error(validation_error)
    }
    const { data, error: patch_error } = await client.PATCH(
      "/api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}",
      {
        params: { path: { project_id, task_id, eval_id } },
        body: {
          output_score_display_names: {
            [score_key]: display_name.trim(),
          },
        },
      },
    )
    if (patch_error) {
      throw patch_error
    }
    const saved_score = data.output_scores.find(
      (s) => string_to_json_key(s.name) === score_key,
    )
    if (saved_score) {
      dispatch("saved", {
        eval_id,
        score_key,
        display_name: score_display_name(saved_score),
      })
    }
    dialog?.close()
  }
</script>

<Dialog bind:this={dialog} title="Rename Score">
  {#if loading}
    <div class="flex justify-center py-8">
      <div class="loading loading-spinner loading-md"></div>
    </div>
  {:else if score}
    <FormContainer
      submit_label="Save"
      bind:error
      bind:submitting
      on:submit={async () => {
        try {
          await save()
        } catch (e) {
          error = createKilnError(e)
        } finally {
          submitting = false
        }
      }}
    >
      <FormElement
        id="score_display_name"
        label="Score Name"
        description="Shown wherever this score appears."
        inputType="input"
        {max_length}
        validator={validate_display_name}
        bind:value={display_name}
      />
    </FormContainer>
  {:else if error}
    <div class="text-error text-sm">{error.getMessage()}</div>
  {/if}
</Dialog>
