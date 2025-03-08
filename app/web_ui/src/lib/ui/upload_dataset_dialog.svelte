<script lang="ts">
  import { client } from "$lib/api_client"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { page } from "$app/stores"
  import Dialog from "$lib/ui/dialog.svelte"

  export let onImportCompleted: () => void

  const dataset_type_accepts = {
    csv: [".csv"],
  }

  let error: KilnError | null = null
  let loading = false
  let selected_file: File | null = null
  let dataset_type: "csv" | null = "csv"

  $: project_id = $page.params.project_id
  $: task_id = $page.params.task_id

  function handleFileSelect(event: Event) {
    const input = event.target as HTMLInputElement
    if (input.files && input.files[0]) {
      selected_file = input.files[0]
    }
  }

  async function handleUpload(): Promise<boolean> {
    if (!selected_file || !dataset_type) {
      return false
    }

    loading = true
    try {
      const formData = new FormData()
      formData.append("file", selected_file)
      formData.append("dataset_type", dataset_type!)

      const { error } = await client.POST(
        "/api/projects/{project_id}/tasks/{task_id}/runs/bulk_upload",
        {
          params: { path: { project_id, task_id } },
          // @ts-expect-error - formData type mismatch
          body: formData,
        },
      )

      if (error) {
        throw error
      }

      selected_file = null

      onImportCompleted()

      return true
    } catch (e) {
      console.error("Upload failed:", e)
      error = createKilnError(e)
      return false
    } finally {
      loading = false
    }
  }

  let dialog: Dialog | null = null

  export function show() {
    dialog?.show()
    selected_file = null
  }

  export function close() {
    dialog?.close()
    selected_file = null
    error = null
    loading = false
    return true
  }

  function handleCancel() {
    close()
    return true
  }
</script>

<Dialog
  bind:this={dialog}
  title="Upload Dataset"
  action_buttons={[
    { label: "Cancel", isCancel: true, action: () => handleCancel() },
    {
      label: "Upload",
      asyncAction: () => handleUpload(),
      disabled: !selected_file,
    },
  ]}
>
  <div class="text-sm">
    {#if loading}
      <div class="w-full min-h-[50vh] flex justify-center items-center">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else}
      <p class="mb-4">Select the type of dataset you want to upload.</p>
      <div class="form-control">
        <label class="label cursor-pointer flex flex-row gap-3">
          <input
            type="radio"
            name="radio-input-schema-dataset-type"
            class="radio"
            value="csv"
            bind:group={dataset_type}
          />
          <span class="label-text text-left grow">CSV</span>
        </label>
      </div>
      {#if dataset_type}
        <p class="mb-4">Select a dataset file to upload:</p>
        <input
          type="file"
          class="file-input file-input-bordered w-full"
          on:change={handleFileSelect}
          accept={dataset_type_accepts[dataset_type].join(",")}
        />
        {#if selected_file}
          <p class="mt-2 text-sm text-gray-500">
            Selected: {selected_file.name}
          </p>
        {/if}
      {/if}
    {/if}
  </div>
  {#if error}
    <div class="text-error text-sm">
      {error.getMessage() || "An unknown error occurred"}
    </div>
  {/if}
</Dialog>
