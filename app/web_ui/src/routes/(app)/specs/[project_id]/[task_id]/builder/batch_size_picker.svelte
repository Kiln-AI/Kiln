<script lang="ts">
  // Step 4's dataset size rows: the profile, and Custom's own item count.
  import FormElement from "$lib/utils/form_element.svelte"
  import KilnProBatchCountRow from "../../../../generate/[project_id]/[task_id]/kiln_pro_batch_count_row.svelte"
  import {
    profile_options,
    CUSTOM_MAX,
    CUSTOM_MIN,
    type BatchSize,
  } from "./batch_profiles"

  export let size: BatchSize

  const dataset_size_options = [{ options: profile_options() }]
</script>

<FormElement
  id="dataset_size"
  label="Dataset Size"
  inputType="fancy_select"
  fancy_select_options={dataset_size_options}
  bind:value={size.profile}
/>
{#if size.profile === "custom"}
  <KilnProBatchCountRow
    label="Item Count"
    bind:value={size.custom_count}
    min={CUSTOM_MIN}
    max={CUSTOM_MAX}
  />
{/if}
