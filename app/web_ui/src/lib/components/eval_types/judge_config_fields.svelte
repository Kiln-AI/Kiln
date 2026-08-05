<script lang="ts">
  import {
    getV2EvalTypeMetadata,
    type V2EvalType,
    type EvalTypeFormApi,
  } from "$lib/utils/eval_types/registry"
  import type { V2EvalConfigProperties } from "$lib/api/v2_eval_api"
  import type { EvalOutputScore } from "$lib/types"

  /**
   * Renders the form fields for a single non-LLM judge type, wiring up the
   * per-type props each form expects. Shared by the eval-config builder (adding
   * a judge to an existing eval) and the spec builder (creating an eval and its
   * judge together), so the two can't drift.
   *
   * LLM judge is deliberately not handled here: it doesn't implement
   * EvalTypeFormApi and needs model/algo/prompt state its callers own.
   */
  export let eval_config_type: V2EvalType
  export let project_id: string = ""
  export let task_id: string = ""
  export let output_scores: EvalOutputScore[] | undefined = undefined
  export let reference_candidate_keys: string[] = []
  // Creation flow only: the code judge seeds its starter code with a static
  // "score_name" placeholder instead of chasing the still-being-typed eval name.
  export let code_placeholder_score_key: boolean = false

  // Bound out to callers that gate on the current draft (e.g. the save-after-test
  // rule keys off code edits, and the reference-key dropdown off the expression).
  export let code_string: string | undefined = undefined
  export let required_reference_fields: string[] = []
  export let output_value_expression: string | null = null

  $: metadata = getV2EvalTypeMetadata(eval_config_type)

  // svelte:component yields a generic instance, so keep a loose ref and cast.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let form_ref: any
  $: form = form_ref as EvalTypeFormApi | undefined

  export function getProperties(): V2EvalConfigProperties {
    if (!form) {
      throw new Error("Judge form is not ready.")
    }
    return form.getProperties()
  }

  export function validate(): string | null {
    return form?.validate?.() ?? null
  }
</script>

{#if eval_config_type === "code_eval"}
  <svelte:component
    this={metadata.createFormComponent}
    bind:this={form_ref}
    bind:code_string
    {output_scores}
    placeholder_score_key={code_placeholder_score_key}
  />
{:else if eval_config_type === "exact_match" || eval_config_type === "contains" || eval_config_type === "set_check"}
  <svelte:component
    this={metadata.createFormComponent}
    bind:this={form_ref}
    {reference_candidate_keys}
    bind:required_reference_fields
    bind:output_value_expression
  />
{:else if eval_config_type === "pattern_match"}
  <svelte:component
    this={metadata.createFormComponent}
    bind:this={form_ref}
    bind:output_value_expression
  />
{:else if eval_config_type === "tool_call_check"}
  <svelte:component
    this={metadata.createFormComponent}
    bind:this={form_ref}
    {project_id}
    {task_id}
  />
{:else}
  <svelte:component this={metadata.createFormComponent} bind:this={form_ref} />
{/if}
