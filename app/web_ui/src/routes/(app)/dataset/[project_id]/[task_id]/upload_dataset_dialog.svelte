<script lang="ts">
  import { client } from "$lib/api_client"
  import { page } from "$app/stores"
  import Dialog from "$lib/ui/dialog.svelte"

  export let onImportCompleted: () => void
  export let tag_splits: Record<string, number> | null = null

  let selected_file: File | null = null

  $: project_id = $page.params.project_id
  $: task_id = $page.params.task_id

  function handleFileSelect(event: Event) {
    const input = event.target as HTMLInputElement
    if (input.files && input.files[0]) {
      selected_file = input.files[0]
    }
  }

  async function handleUpload(): Promise<boolean> {
    if (!selected_file) {
      return false
    }

    const formData = new FormData()
    formData.append("file", selected_file)
    if (tag_splits) {
      formData.append("splits", JSON.stringify(tag_splits))
    }

    const { error } = await client.POST(
      "/api/projects/{project_id}/tasks/{task_id}/runs/bulk_upload",
      {
        params: {
          path: { project_id, task_id },
        },
        // todo: a transform must be set up to determine how to serialize multipart file uploads
        // see: https://github.com/openapi-ts/openapi-typescript/issues/1214
        body: formData as unknown as { file: string },
      },
    )

    if (error) {
      throw error
    }

    selected_file = null

    onImportCompleted()

    return true
  }

  let dialog: Dialog | null = null

  export function show() {
    dialog?.show()
    selected_file = null
  }

  export function close() {
    dialog?.close()
    selected_file = null
    return true
  }

  function handleCancel() {
    close()
    return true
  }
</script>

<Dialog
  bind:this={dialog}
  title="Upload CSV to Dataset"
  action_buttons={[
    { label: "Cancel", isCancel: true, action: () => handleCancel() },
    {
      label: "Upload",
      asyncAction: () => handleUpload(),
      disabled: !selected_file,
      isPrimary: true,
    },
  ]}
>
  <div class="font-light text-sm">
    <div class="space-y-2">
      <div>
        <p>
          Upload a CSV to add each row to your dataset. The CSV must have a
          header row (<a
            href="https://docs.getkiln.ai/docs/organizing-datasets"
            target="_blank"
            class="link">see docs</a
          >). The following columns are supported:
        </p>
        <ul class="mb-6 ml-4 mt-3 list-disc">
          <li><code>input</code> - Required</li>
          <li><code>output</code> - Required</li>
          <li><code>reasoning</code> - Optional</li>
          <li><code>chain_of_thought</code> - Optional</li>
          <li><code>tags</code> - Optional, comma separated string</li>
        </ul>
      </div>
    </div>
    <input
      type="file"
      class="file-input file-input-bordered w-full"
      on:change={handleFileSelect}
      accept=".csv"
    />
  </div>
</Dialog>
