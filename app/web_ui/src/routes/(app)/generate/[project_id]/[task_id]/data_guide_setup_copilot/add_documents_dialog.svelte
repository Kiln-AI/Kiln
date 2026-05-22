<script lang="ts" context="module">
  // Browser-side text extraction only. We deliberately limit to plaintext-
  // shaped formats so we don't have to ship an extractor in the browser.
  // PDF/DOCX support would need server-side extraction (deferred).
  export const ACCEPTED_EXTENSIONS = [
    ".txt",
    ".text",
    ".md",
    ".markdown",
    ".csv",
    ".tsv",
    ".log",
    ".json",
    ".yaml",
    ".yml",
  ]

  // Per-document char cap. Mirrors the server-side guardrail in
  // ANALYZE_INPUT_DATA_GUIDE_MAX_EXAMPLES * per-doc and total payload sizes.
  export const MAX_DOC_CHARS = 50_000

  export type ExtractedDocument = {
    name: string
    text: string
    truncated: boolean
    file: File
  }
</script>

<script lang="ts">
  import { createEventDispatcher } from "svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import UploadIcon from "$lib/ui/icons/upload_icon.svelte"
  import TrashIcon from "$lib/ui/icons/trash_icon.svelte"

  // Maximum number of *new* documents the parent will accept. Used to clamp
  // selection so we don't add more than fit. -1 = no limit.
  export let max_files: number = -1

  let dialog: Dialog | null = null
  let selected_files: File[] = []
  let file_input: HTMLInputElement
  let drag_over = false
  let unsupported_files_count = 0
  let extraction_error: string | null = null

  const dispatch = createEventDispatcher<{
    add: { documents: ExtractedDocument[] }
  }>()

  export function show() {
    selected_files = []
    unsupported_files_count = 0
    extraction_error = null
    dialog?.show()
  }

  export function close() {
    dialog?.close()
    selected_files = []
    unsupported_files_count = 0
    extraction_error = null
    return true
  }

  function file_supported(file: File): boolean {
    if (!file) return false
    const ext = ("." + (file.name.split(".").pop() || "")).toLowerCase()
    return ACCEPTED_EXTENSIONS.includes(ext)
  }

  function add_files(files: File[]) {
    const supported = files.filter(file_supported)
    const unsupported = files.filter((f) => !file_supported(f))

    const new_unsupported = unsupported.filter(
      (file) =>
        !selected_files.some(
          (existing) =>
            existing.name === file.name && existing.size === file.size,
        ),
    ).length
    unsupported_files_count += new_unsupported

    let new_files = supported.filter(
      (file) =>
        !selected_files.some(
          (existing) =>
            existing.name === file.name && existing.size === file.size,
        ),
    )

    if (max_files >= 0) {
      const remaining = Math.max(0, max_files - selected_files.length)
      if (new_files.length > remaining) {
        new_files = new_files.slice(0, remaining)
      }
    }

    selected_files = [...selected_files, ...new_files]
  }

  function remove_file(index: number) {
    selected_files = selected_files.filter((_, i) => i !== index)
  }

  function handle_file_select(event: Event) {
    const input = event.target as HTMLInputElement
    if (input.files) add_files(Array.from(input.files))
    input.value = ""
  }

  function handle_drag_over(event: DragEvent) {
    event.preventDefault()
    drag_over = true
  }

  function handle_drag_leave(event: DragEvent) {
    event.preventDefault()
    drag_over = false
  }

  function handle_drop(event: DragEvent) {
    event.preventDefault()
    drag_over = false
    if (event.dataTransfer?.files) {
      add_files(Array.from(event.dataTransfer.files))
    }
  }

  function open_file_dialog() {
    file_input?.click()
  }

  async function handle_add(): Promise<boolean> {
    extraction_error = null
    if (selected_files.length === 0) return false

    const documents: ExtractedDocument[] = []
    const failed: string[] = []
    for (const file of selected_files) {
      try {
        const text = await file.text()
        if (!text.trim()) {
          failed.push(`${file.name} (empty)`)
          continue
        }
        const truncated = text.length > MAX_DOC_CHARS
        documents.push({
          name: file.name,
          text: truncated ? text.slice(0, MAX_DOC_CHARS) : text,
          truncated,
          file,
        })
      } catch {
        failed.push(`${file.name} (read failed)`)
      }
    }

    if (documents.length === 0) {
      extraction_error =
        failed.length > 0
          ? `No documents could be extracted: ${failed.join(", ")}`
          : "No documents to add."
      return false
    }

    dispatch("add", { documents })
    if (failed.length > 0) {
      // Keep dialog open with a warning so the user sees which were skipped.
      extraction_error = `Some files were skipped: ${failed.join(", ")}`
      selected_files = selected_files.filter((f) =>
        failed.some((s) => s.startsWith(f.name + " ")),
      )
      return false
    }
    close()
    return true
  }
</script>

<Dialog
  bind:this={dialog}
  title="Add Documents"
  sub_subtitle="Add example inputs from text documents, one document per input."
  action_buttons={[
    { label: "Cancel", isCancel: true, action: () => close() },
    {
      label:
        selected_files.length > 1
          ? `Add ${selected_files.length} Files`
          : "Add",
      asyncAction: () => handle_add(),
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
          <li>Plain text: .txt, .md, .markdown, .text, .log</li>
          <li>Structured text: .csv, .tsv, .json, .yaml, .yml</li>
        </ul>
        <p class="text-xs text-gray-500 mt-2">
          Each document is capped at {MAX_DOC_CHARS.toLocaleString()}
          characters.
        </p>
      </div>

      <div class="pb-2">
        <div
          class="border-2 border-dashed rounded-lg p-8 text-center transition-colors cursor-pointer {drag_over
            ? 'border-primary bg-primary/5'
            : 'border-gray-300 hover:border-gray-400'}"
          on:dragover={handle_drag_over}
          on:dragleave={handle_drag_leave}
          on:drop={handle_drop}
          on:click={open_file_dialog}
          role="button"
          tabindex="0"
          on:keydown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault()
              open_file_dialog()
            }
          }}
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

        <input
          bind:this={file_input}
          type="file"
          multiple
          class="hidden"
          on:change={handle_file_select}
          accept={ACCEPTED_EXTENSIONS.join(",")}
        />

        {#if unsupported_files_count > 0}
          <div class="text-error text-sm mt-2">
            {unsupported_files_count} file{unsupported_files_count === 1
              ? ""
              : "s"} skipped due to unsupported format
          </div>
        {/if}
        {#if max_files >= 0 && selected_files.length >= max_files}
          <div class="text-warning text-sm mt-2">
            Maximum of {max_files} additional file{max_files === 1 ? "" : "s"} reached.
          </div>
        {/if}
      </div>

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
                  class="ml-2 text-gray-500 hover:text-gray-700 h-4 w-4 flex-shrink-0"
                  on:click={() => remove_file(index)}
                >
                  <TrashIcon />
                </button>
              </div>
            {/each}
          </div>
        </div>
      {/if}

      {#if extraction_error}
        <div class="text-error text-sm">{extraction_error}</div>
      {/if}
    </div>
  </div>
</Dialog>
