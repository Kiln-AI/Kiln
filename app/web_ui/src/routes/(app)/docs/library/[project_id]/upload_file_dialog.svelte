<script lang="ts">
  import { client } from "$lib/api_client"
  import { page } from "$app/stores"
  import Dialog from "$lib/ui/dialog.svelte"
  import TagPicker from "$lib/ui/tag_picker.svelte"
  import { ragProgressStore } from "$lib/stores/rag_progress_store"
  import { load_document_tags } from "$lib/stores/document_tag_store"
  import type { BulkCreateDocumentsResponse } from "$lib/types"
  import posthog from "posthog-js"
  import { createKilnError, KilnError } from "$lib/utils/error_handlers"
  import UploadIcon from "$lib/ui/icons/upload_icon.svelte"
  import TrashIcon from "$lib/ui/icons/trash_icon.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import ExtractorPicker from "$lib/components/extractor_picker.svelte"

  export let onUploadCompleted: (
    result: BulkCreateDocumentsResponse | null,
  ) => void
  // When true, the dialog stays open after a successful upload and shows an
  // inline extractor picker so the just-uploaded docs can be converted to text
  // without a second dialog. Opt-in; other callers keep the existing behavior.
  export let extract_after_upload: boolean = false
  // Tags scoping the inline extraction run (the uploaded docs must carry these;
  // pass the same tags as `auto_tags`).
  export let extract_tags: string[] = []
  // Called when the inline extraction run completes.
  export let onExtractionComplete:
    | ((extractor_config_id: string, error_count: number) => void)
    | null = null
  // When set, the tag picker is hidden and these tags are auto-applied to every
  // uploaded file (a short note is shown instead). Used by flows that curate
  // documents under a fixed tag, e.g. the Data Guide sample uploader.
  export let auto_tags: string[] = []
  // Skip the in-dialog success screen and close as soon as the upload finishes.
  // Callers that drive their own post-upload UI (e.g. adding the docs as
  // samples) use this together with the onUploadCompleted result.
  export let close_on_success: boolean = false
  // Subtitle shown under the dialog title. Defaults to the document library
  // copy; flows like the Data Guide override it to describe their own context.
  export let subtitle: string = "Add files to your project's document library"

  let upload_error: KilnError | null = null
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

  $: project_id = $page.params.project_id!

  function handleFileSelect(event: Event) {
    const input = event.target as HTMLInputElement
    if (input.files) {
      addFiles(Array.from(input.files))
    }
  }

  function addFiles(files: File[]) {
    const validFiles = files.filter((file) => file_supported(file))
    const unsupportedFiles = files.filter((file) => !file_supported(file))

    // count new unsupported files (not already in the count)
    const newUnsupportedCount = unsupportedFiles.filter(
      (file) =>
        !selected_files.some(
          (existing) =>
            existing.name === file.name && existing.size === file.size,
        ),
    ).length

    unsupported_files_count += newUnsupportedCount

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
  let upload_result: BulkCreateDocumentsResponse | null = null
  let show_upload_result = false
  let unsupported_files_count = 0
  let show_success_dialog = false
  // When `extract_after_upload` is set, the extractor picker is shown inline at
  // the bottom of the dialog once files are selected. Sticky so it stays mounted
  // across the upload (which clears selected_files) and the extraction run.
  let extractor_picker: ExtractorPicker
  let extracting = false
  let picker_active = false
  $: if (extract_after_upload && selected_files.length > 0) {
    picker_active = true
  }

  // tags
  let selected_tags: string[] = []
  let tag_picker: TagPicker | null = null

  async function handleUpload(): Promise<boolean> {
    tag_picker?.flush_pending_tag()

    upload_error = null
    upload_in_progress = true
    upload_progress = 0
    upload_total = selected_files.length
    upload_result = null
    show_upload_result = false
    show_success_dialog = false

    try {
      const success = await uploadFiles()
      // Keep the dialog open when we're showing the success screen.
      if (success && show_success_dialog) {
        return false
      }
      return success
    } catch (e) {
      upload_error = createKilnError(e)
      return false
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

    const tags_to_apply = auto_tags.length > 0 ? auto_tags : selected_tags
    if (tags_to_apply.length > 0) {
      tags_to_apply.forEach((tag) => {
        formData.append("tags", tag)
      })
    }

    const { data, error } = await client.POST(
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

    upload_result = data
    show_upload_result = true
    // In inline-extraction mode the picker drives the close; never show the
    // plain success screen there.
    show_success_dialog = !close_on_success && !extract_after_upload

    const uploaded_files = selected_files
    selected_files = []
    onUploadCompleted(data)

    // reload document tags for the project - because total counts have changed
    // and we cannot know which ones due to partial upload rejection possibly
    // happening on the backend
    await load_document_tags(project_id, { invalidate_cache: true })

    ragProgressStore.run_all_rag_configs(project_id).catch((error) => {
      console.error("Error running all rag configs", error)
    })

    posthog.capture("add_documents", {
      file_count: uploaded_files.length,
      file_count_summary: file_count_summary(uploaded_files),
      kind_counts: kind_counts(uploaded_files),
    })

    return true
  }

  // before_run hook for the inline extractor picker: upload the selected files
  // (tagging them via auto_tags) so the extraction run, scoped by extract_tags,
  // catches them. A no-op on retry, where the files were already uploaded and
  // selected_files has been cleared. Throws on failure so the picker aborts and
  // surfaces the error.
  async function upload_for_extraction(): Promise<void> {
    if (selected_files.length === 0) return
    tag_picker?.flush_pending_tag()
    upload_error = null
    upload_in_progress = true
    upload_progress = 0
    upload_total = selected_files.length
    try {
      const ok = await uploadFiles()
      if (!ok) throw new KilnError("Upload failed", null)
    } finally {
      upload_in_progress = false
      upload_progress = 0
      upload_total = 0
    }
  }

  function file_count_summary(files: File[]): Record<string, number> {
    try {
      let summary: Record<string, number> = {}
      let recognized_file_types_count = 0
      for (const filetype of supported_file_types) {
        const count = files.filter((file) =>
          file.name.toLowerCase().endsWith(filetype),
        ).length
        if (count > 0) {
          summary[filetype] = count
          recognized_file_types_count += count
        }
      }
      let unrecognized_file_types_count =
        files.length - recognized_file_types_count
      summary["unknown_type"] = unrecognized_file_types_count
      return summary
    } catch (e) {
      console.error(e)
      return {}
    }
  }

  function infer_kind(file: File): string {
    const mime = file.type || ""
    if (mime.startsWith("image/")) return "image"
    if (mime.startsWith("video/")) return "video"
    if (mime.startsWith("audio/")) return "audio"

    // documents by mime
    if (
      mime === "application/pdf" ||
      mime === "text/plain" ||
      mime === "text/markdown" ||
      mime === "text/html" ||
      mime === "text/csv"
    ) {
      return "document"
    }

    // fallback by extension
    const ext = ("." + (file.name.split(".").pop() || "")).toLowerCase()
    if ([".pdf", ".txt", ".md", ".html"].includes(ext)) return "document"
    if ([".jpg", ".jpeg", ".png"].includes(ext)) return "image"
    if ([".mp4", ".mov"].includes(ext)) return "video"
    if ([".mp3", ".wav", ".ogg"].includes(ext)) return "audio"

    return "unknown"
  }

  function kind_counts(files: File[]): Record<string, number> {
    try {
      let summary: Record<string, number> = {}
      for (const file of files) {
        const kind = infer_kind(file)
        summary[kind] = (summary[kind] || 0) + 1
      }
      return summary
    } catch (e) {
      console.error(e)
      return {}
    }
  }

  let dialog: Dialog | null = null

  export function show() {
    dialog?.show()
    selected_files = []
    upload_result = null
    show_upload_result = false
    show_success_dialog = false
    picker_active = false
    extractor_picker?.reset()
    unsupported_files_count = 0
    selected_tags = []
  }

  export function close() {
    dialog?.close()
    selected_files = []
    upload_result = null
    show_upload_result = false
    show_success_dialog = false
    picker_active = false
    extractor_picker?.reset()
    unsupported_files_count = 0
    selected_tags = []
    return true
  }

  function handle_extraction_complete(
    event: CustomEvent<{ extractor_config_id: string; error_count: number }>,
  ) {
    onExtractionComplete?.(
      event.detail.extractor_config_id,
      event.detail.error_count,
    )
    close()
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
  title={show_success_dialog
    ? "Completed"
    : upload_in_progress || extracting
      ? "Processing Documents"
      : "Add Documents"}
  sub_subtitle={show_success_dialog ? undefined : subtitle}
  action_buttons={extract_after_upload
    ? []
    : show_success_dialog
      ? [{ label: "Close", isPrimary: true, action: () => close() }]
      : [
          {
            label:
              selected_files.length > 1
                ? `Add ${selected_files.length} Files`
                : "Add",
            asyncAction: () => handleUpload(),
            disabled: selected_files.length === 0,
            isPrimary: true,
          },
        ]}
>
  <div class="font-light text-sm">
    <div class="space-y-4">
      {#if show_success_dialog && upload_result}
        <!-- Success state content -->
        <div class="text-center space-y-2">
          <p class="text-gray-500 text-sm">
            {upload_result.created_documents.length} file{upload_result
              .created_documents.length === 1
              ? ""
              : "s"} added successfully
            {#if upload_result.failed_files.length > 0}
              <br />
              {upload_result.failed_files.length} file{upload_result
                .failed_files.length === 1
                ? ""
                : "s"} failed
            {/if}
          </p>
        </div>
      {:else if !extracting}
        <!-- Normal upload state content -->
        <div>
          <p>The following file types are supported:</p>
          <ul class="list-disc list-inside mt-2">
            <li>Documents: .pdf, .txt, .md, .html</li>
            <li>Images: .jpg, .jpeg, .png</li>
            <li>Videos: .mp4, .mov</li>
            <li>Audio: .mp3, .wav, .ogg</li>
          </ul>
        </div>
      {/if}

      {#if !show_success_dialog && !extracting}
        <div class="pb-2">
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
            on:keydown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault()
                openFileDialog()
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

          <!-- Hidden file input -->
          <input
            bind:this={file_input}
            type="file"
            multiple
            class="hidden"
            on:change={handleFileSelect}
            accept={supported_file_types.join(",")}
          />

          {#if unsupported_files_count > 0}
            <div class="text-error text-sm">
              {unsupported_files_count} file{unsupported_files_count === 1
                ? ""
                : "s"} skipped due to unsupported format
            </div>
          {/if}
        </div>

        <!-- Tag selection -->
        {#if auto_tags.length === 0}
          <div>
            <FormElement
              inputType="header_only"
              label="Tags"
              id="tags_section"
              description="Add tags to organize your documents"
              info_description="Any tags set here will be added to each document you add. Tags can be used to filter your document set."
              optional={true}
              value=""
            />
            <TagPicker
              bind:this={tag_picker}
              tags={selected_tags}
              tag_type="doc"
              {project_id}
              initial_expanded={true}
              hide_dropdown_after_select={false}
              show_close_button={false}
              on:tags_changed={(event) => {
                selected_tags = event.detail.current
              }}
            />
          </div>
        {:else}
          <div class="text-sm text-gray-500">
            These files will be saved to your
            <a
              href={`/docs/library/${project_id}`}
              target="_blank"
              rel="noopener"
              class="link">Document Library</a
            >
            with the tag
            {#each auto_tags as tag, i}
              <code class="bg-base-200 px-1 py-px rounded">{tag}</code>{i <
              auto_tags.length - 1
                ? ", "
                : ""}
            {/each}
            so you can find them later.
          </div>
        {/if}

        {#if show_upload_result && upload_result}
          {#if upload_result.created_documents.length > 0}
            <div class="text-success text-sm">
              {upload_result.created_documents.length} document{upload_result
                .created_documents.length === 1
                ? ""
                : "s"} added successfully
            </div>
          {/if}
          {#if upload_result.failed_files.length > 0}
            <div class="text-error text-sm">
              {upload_result.failed_files.length} document{upload_result
                .failed_files.length === 1
                ? ""
                : "s"} failed to be added
            </div>
          {/if}
        {/if}
      {/if}

      {#if !show_success_dialog && !extracting}
        <!-- Selected files list -->
        {#if selected_files.length > 0}
          <div class="space-y-2">
            <h4 class="font-medium">
              Selected Files ({selected_files.length})
            </h4>
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
              <span>Adding files...</span>
              <span>{upload_progress}/{upload_total}</span>
            </div>
            <progress
              class="progress progress-primary w-full"
              value={upload_progress}
              max={upload_total}
            ></progress>
          </div>
        {/if}
      {/if}

      {#if extract_after_upload && picker_active}
        <div class="mt-2">
          <ExtractorPicker
            bind:this={extractor_picker}
            bind:extracting
            target_tags={extract_tags}
            preselect_default_extractor={true}
            show_run_button={true}
            description="Select an extractor configuration to convert uploaded documents into text."
            before_run={upload_for_extraction}
            on:extraction_complete={handle_extraction_complete}
          />
        </div>
      {/if}

      {#if upload_error}
        <div class="text-error text-sm">
          {upload_error.getMessage() || "An unknown error occurred"}
        </div>
      {/if}
    </div>
  </div>
</Dialog>
