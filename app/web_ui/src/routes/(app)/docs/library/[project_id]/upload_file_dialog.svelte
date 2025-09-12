<script lang="ts">
  import { client } from "$lib/api_client"
  import { page } from "$app/stores"
  import Dialog from "$lib/ui/dialog.svelte"
  import TrashIcon from "$lib/ui/trash_icon.svelte"
  import UploadIcon from "$lib/ui/upload_icon.svelte"
  import { ragProgressStore } from "$lib/stores/rag_progress_store"

  export let onUploadCompleted: () => void

  let selected_files: File[] = []
  let file_input: HTMLInputElement
  let drag_over = false
  const supported_file_types = [
    ".pdf",
    ".txt",
    ".md",
    ".html",
    ".jpg",
    ".jpeg",
    ".png",
    ".mp4",
    ".mov",
    ".mp3",
    ".wav",
    ".ogg",
  ]

  $: project_id = $page.params.project_id

  function handleFileSelect(event: Event) {
    const input = event.target as HTMLInputElement
    if (input.files) {
      addFiles(Array.from(input.files))
    }
  }

  function addFiles(files: File[]) {
    const validFiles = files.filter((file) => file_supported(file))
    const newFiles = validFiles.filter(
      (file) =>
        !selected_files.some(
          (existing) =>
            existing.name === file.name && existing.size === file.size,
        ),
    )
    selected_files = [...selected_files, ...newFiles]
  }

  function removeFile(index: number) {
    selected_files = selected_files.filter((_, i) => i !== index)
  }

  function handleDragOver(event: DragEvent) {
    event.preventDefault()
    drag_over = true
  }

  function handleDragLeave(event: DragEvent) {
    event.preventDefault()
    drag_over = false
  }

  function handleDrop(event: DragEvent) {
    event.preventDefault()
    drag_over = false

    if (event.dataTransfer?.files) {
      addFiles(Array.from(event.dataTransfer.files))
    }
  }

  function openFileDialog() {
    file_input?.click()
  }

  let upload_in_progress: boolean = false
  let upload_progress = 0
  let upload_total = 0

  async function handleUpload(): Promise<boolean> {
    upload_in_progress = true
    upload_progress = 0
    upload_total = selected_files.length

    try {
      const success = await uploadFiles()
      return success
    } finally {
      upload_in_progress = false
      upload_progress = 0
      upload_total = 0
    }
  }

  async function uploadFiles(): Promise<boolean> {
    if (selected_files.length === 0) {
      return false
    }

    const formData = new FormData()

    selected_files.forEach((file) => {
      formData.append("files", file)
      formData.append(`names`, file.name)
    })

    const { error } = await client.POST(
      "/api/projects/{project_id}/documents/bulk",
      {
        params: {
          path: { project_id },
        },
        // todo: a transform must be set up to determine how to serialize multipart file uploads
        // see: https://github.com/openapi-ts/openapi-typescript/issues/1214
        body: formData as unknown as {
          files: string[]
          names: string[]
        },
      },
    )

    if (error) {
      throw error
    }

    selected_files = []
    onUploadCompleted()

    ragProgressStore.run_all_rag_configs(project_id)

    return true
  }

  let dialog: Dialog | null = null

  export function show() {
    dialog?.show()
    selected_files = []
  }

  export function close() {
    dialog?.close()
    selected_files = []
    return true
  }

  function handleCancel() {
    close()
    return true
  }

  function file_supported(file: File): boolean {
    if (!file) {
      return false
    }
    return supported_file_types.includes(
      ("." + (file.name.split(".").pop() || "")).toLowerCase(),
    )
  }
</script>

<Dialog
  bind:this={dialog}
  title={upload_in_progress ? "Processing Documents" : "Add Documents"}
  sub_subtitle="Add files to your project's document store."
  action_buttons={[
    { label: "Cancel", isCancel: true, action: () => handleCancel() },
    {
      label:
        selected_files.length > 1
          ? `Upload ${selected_files.length} Files`
          : "Upload",
      asyncAction: () => handleUpload(),
      disabled: selected_files.length === 0,
      isPrimary: true,
    },
  ]}
>
  <div class="font-light text-sm">
    <div class="space-y-4">
      <div>
        <p>The following file types are supported:</p>
        <ul class="list-disc list-inside mt-2">
          <li>Documents: .pdf, .txt, .md, .html</li>
          <li>Images: .jpg, .jpeg, .png</li>
          <li>Videos: .mp4, .mov</li>
          <li>Audio: .mp3, .wav, .ogg</li>
        </ul>
      </div>

      <!-- Dropzone -->
      <div
        class="border-2 border-dashed rounded-lg p-8 text-center transition-colors cursor-pointer {drag_over
          ? 'border-primary bg-primary/5'
          : 'border-gray-300 hover:border-gray-400'}"
        on:dragover={handleDragOver}
        on:dragleave={handleDragLeave}
        on:drop={handleDrop}
        on:click={openFileDialog}
        role="button"
        tabindex="0"
        on:keydown={(e) => e.key === "Enter" && openFileDialog()}
      >
        <div class="space-y-2">
          <div class="w-10 h-10 mx-auto text-gray-500">
            <UploadIcon />
          </div>
          <div>
            <p class="text-gray-500">Drop files here or click to select</p>
          </div>
        </div>
      </div>

      <!-- Hidden file input -->
      <input
        bind:this={file_input}
        type="file"
        multiple
        class="hidden"
        on:change={handleFileSelect}
        accept={supported_file_types.join(",")}
      />

      <!-- Selected files list -->
      {#if selected_files.length > 0}
        <div class="space-y-2">
          <h4 class="font-medium">Selected Files ({selected_files.length})</h4>
          <div class="max-h-40 overflow-y-auto space-y-1">
            {#each selected_files as file, index}
              <div
                class="flex items-center justify-between p-2 bg-gray-50 rounded"
              >
                <div class="flex items-center space-x-2 flex-1 min-w-0">
                  <img
                    src="/images/file.svg"
                    alt="File"
                    class="h-4 w-4 text-gray-500 flex-shrink-0"
                  />
                  <span class="text-sm truncate" title={file.name}
                    >{file.name}</span
                  >
                  <span class="text-xs text-gray-500 flex-shrink-0"
                    >({Math.round(file.size / 1024)} KB)</span
                  >
                </div>
                <button
                  type="button"
                  class="ml-2 text-red-500 hover:text-red-700 h-4 w-4 flex-shrink-0"
                  on:click={() => removeFile(index)}
                >
                  <TrashIcon />
                </button>
              </div>
            {/each}
          </div>
        </div>
      {/if}

      {#if upload_in_progress && upload_total > 0}
        <div class="space-y-2">
          <div class="flex justify-between text-sm">
            <span>Uploading files...</span>
            <span>{upload_progress}/{upload_total}</span>
          </div>
          <progress
            class="progress progress-primary w-full"
            value={upload_progress}
            max={upload_total}
          ></progress>
        </div>
      {/if}
    </div>
  </div>
</Dialog>
