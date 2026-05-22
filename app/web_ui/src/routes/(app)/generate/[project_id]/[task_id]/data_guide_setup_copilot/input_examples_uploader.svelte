<script lang="ts" context="module">
  // Each entry funnels into a single `text` string sent to the analyze
  // endpoint. `source` and `label` exist for display only — the wire format is
  // just `text`.
  export type InputExampleEntry = {
    source: "upload" | "manual" | "task_run"
    label: string
    text: string
  }

  export const MAX_TOTAL_ENTRIES = 50
</script>

<script lang="ts">
  import { createEventDispatcher } from "svelte"
  import TableActionMenu from "$lib/ui/table_action_menu.svelte"
  import ClampedText from "$lib/ui/clamped_text.svelte"
  import SeeAllDialog from "$lib/ui/see_all_dialog.svelte"
  import { formatExpandedContent } from "$lib/utils/format_expanded_content"
  import AddExampleDialog from "../data_guide_setup/add_example_dialog.svelte"
  import type { GuideSample } from "../data_guide_setup/guide_setup_form.svelte"
  import AddDocumentsDialog, {
    type ExtractedDocument,
  } from "./add_documents_dialog.svelte"
  import Callout from "$lib/ui/callout.svelte"
  import { client } from "$lib/api_client"

  // Tag applied to documents persisted to the Document Library from this
  // uploader. Lets users find / curate the doc that seeded a Data Guide later.
  const DATA_GUIDE_DOC_TAG = "data_guide_example"

  export let project_id: string
  export let task_id: string
  export let entries: InputExampleEntry[] = []

  let upload_warning: string | null = null
  let add_example_dialog: AddExampleDialog
  let add_documents_dialog: AddDocumentsDialog

  const dispatch = createEventDispatcher<{
    change: { entries: InputExampleEntry[] }
  }>()

  function emit_change() {
    dispatch("change", { entries })
  }

  function open_add_example_dialog() {
    add_example_dialog?.open_add()
  }

  function handle_request_documents() {
    // AddExampleDialog already closes itself when "From Documents" is picked;
    // open the docs dialog as a follow-on so the user lands in a single visible flow.
    upload_warning = null
    add_documents_dialog?.show()
  }

  function handle_example_submit(
    event: CustomEvent<{
      sample: GuideSample
      index: number
      mode: "add" | "edit"
    }>,
  ) {
    const { sample } = event.detail
    if (!sample.input.trim()) return
    const entry: InputExampleEntry = {
      source: sample.task_run_id ? "task_run" : "manual",
      label: sample.task_run_id
        ? `Existing run · ${sample.task_run_id.slice(0, 6)}`
        : `Manual ${entries.filter((e) => e.source === "manual").length + 1}`,
      text: sample.input,
    }
    entries = [...entries, entry]
    emit_change()
  }

  function handle_documents_added(
    event: CustomEvent<{ documents: ExtractedDocument[] }>,
  ) {
    upload_warning = null
    const { documents } = event.detail
    const remaining = MAX_TOTAL_ENTRIES - entries.length
    const dropped =
      documents.length > remaining ? documents.length - remaining : 0
    const accepted = documents.slice(0, Math.max(0, remaining))
    const new_entries: InputExampleEntry[] = accepted.map((d) => ({
      source: "upload",
      label: d.truncated ? `${d.name} (truncated)` : d.name,
      text: d.text,
    }))
    entries = [...entries, ...new_entries]
    if (dropped > 0) {
      upload_warning = `${dropped} file${dropped === 1 ? "" : "s"} skipped — entry limit (${MAX_TOTAL_ENTRIES}) reached.`
    }
    emit_change()
    // Fire-and-forget: persist the accepted files to the Document Library so
    // they appear under the data_guide_example tag for later curation. A
    // failure here must NOT block the analyze flow — the user's primary
    // action is to draft a guide, not to manage their library.
    persist_uploaded_documents(accepted.map((d) => d.file))
  }

  async function persist_uploaded_documents(files: File[]) {
    if (files.length === 0) return
    const formData = new FormData()
    files.forEach((file) => {
      formData.append("files", file)
      formData.append("names", file.name)
    })
    formData.append("tags", DATA_GUIDE_DOC_TAG)
    try {
      const { error } = await client.POST(
        "/api/projects/{project_id}/documents/bulk",
        {
          params: { path: { project_id } },
          // openapi-typescript can't serialize multipart uploads from the
          // generated body type. Cast to satisfy the type checker; the runtime
          // FormData is what FastAPI's UploadFile expects.
          body: formData as unknown as { files: string[]; names: string[] },
        },
      )
      if (error) {
        console.error(
          "Failed to persist uploaded documents to Document Library:",
          error,
        )
      }
    } catch (e) {
      console.error(
        "Failed to persist uploaded documents to Document Library:",
        e,
      )
    }
  }

  function remove_entry(index: number) {
    entries = entries.filter((_, i) => i !== index)
    emit_change()
  }

  let see_all_dialog: SeeAllDialog

  // Map each entry to a GuideSample shape so the existing AddExampleDialog can
  // filter "Select Existing" against task_runs already added (treats every
  // entry as a candidate input).
  $: existing_examples_for_dialog = entries.map(
    (e): GuideSample => ({ input: e.text }),
  )
  $: remaining_doc_slots = Math.max(0, MAX_TOTAL_ENTRIES - entries.length)
</script>

<div class="flex flex-col gap-3">
  <Callout
    title="Help us generate more realistic inputs."
    description="Kiln Pro analyzes your example inputs to draft data generation guidelines for review."
  >
    <div slot="icon">
      <!-- Uploaded to: SVG Repo, www.svgrepo.com, Generator: SVG Repo Mixer Tools -->
      <svg
        class="w-5 h-5"
        viewBox="0 0 24 24"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <path
          d="M8.03339 3.65784C8.37932 2.78072 9.62068 2.78072 9.96661 3.65785L11.0386 6.37599C11.1442 6.64378 11.3562 6.85576 11.624 6.96137L14.3422 8.03339C15.2193 8.37932 15.2193 9.62068 14.3422 9.96661L11.624 11.0386C11.3562 11.1442 11.1442 11.3562 11.0386 11.624L9.96661 14.3422C9.62067 15.2193 8.37932 15.2193 8.03339 14.3422L6.96137 11.624C6.85575 11.3562 6.64378 11.1442 6.37599 11.0386L3.65784 9.96661C2.78072 9.62067 2.78072 8.37932 3.65785 8.03339L6.37599 6.96137C6.64378 6.85575 6.85576 6.64378 6.96137 6.37599L8.03339 3.65784Z"
          stroke="currentColor"
          stroke-width="1.5"
        />
        <path
          d="M16.4885 13.3481C16.6715 12.884 17.3285 12.884 17.5115 13.3481L18.3121 15.3781C18.368 15.5198 18.4802 15.632 18.6219 15.6879L20.6519 16.4885C21.116 16.6715 21.116 17.3285 20.6519 17.5115L18.6219 18.3121C18.4802 18.368 18.368 18.4802 18.3121 18.6219L17.5115 20.6519C17.3285 21.116 16.6715 21.116 16.4885 20.6519L15.6879 18.6219C15.632 18.4802 15.5198 18.368 15.3781 18.3121L13.3481 17.5115C12.884 17.3285 12.884 16.6715 13.3481 16.4885L15.3781 15.6879C15.5198 15.632 15.632 15.5198 15.6879 15.3781L16.4885 13.3481Z"
          stroke="currentColor"
          stroke-width="1.5"
        />
      </svg>
    </div>
  </Callout>
  <div class="flex flex-wrap items-center justify-between gap-3 mt-4">
    <div class="min-w-0 flex-1">
      <div class="font-medium">Example Inputs</div>
      <div class="text-sm text-gray-500">
        Add examples manually, from documents, or selecting from existing
        examples.
      </div>
    </div>
    <div class="flex flex-row gap-2 shrink-0">
      <button
        type="button"
        class="btn btn-sm whitespace-nowrap {entries.length === 0
          ? 'btn-primary'
          : 'btn-outline'}"
        on:click={open_add_example_dialog}
        disabled={entries.length >= MAX_TOTAL_ENTRIES}
      >
        + Add Example
      </button>
    </div>
  </div>

  {#if upload_warning}
    <div class="text-xs text-warning">{upload_warning}</div>
  {/if}

  {#if entries.length > 0}
    <div class="rounded-lg border">
      <table class="table table-fixed">
        <thead>
          <tr>
            <th>Input</th>
            <th style="width: 50px"></th>
          </tr>
        </thead>
        <tbody>
          {#each entries as entry, i}
            {@const text_content = formatExpandedContent(entry.text)}
            <tr>
              <td class="py-2">
                <ClampedText
                  content={text_content.isJson ? "" : text_content.value}
                  html_content={text_content.isJson ? text_content.value : null}
                  on:see_all={() =>
                    see_all_dialog.show(entry.label, entry.text)}
                />
              </td>
              <td class="py-2 p-0">
                <div class="dropdown dropdown-end dropdown-hover">
                  <TableActionMenu
                    items={[
                      { label: "Remove", onclick: () => remove_entry(i) },
                    ]}
                  />
                </div>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {:else}
    <div
      class="rounded-lg border border-dashed border-gray-300 p-8 text-center text-sm text-gray-400"
    >
      No example inputs
    </div>
  {/if}
</div>

<AddExampleDialog
  bind:this={add_example_dialog}
  {project_id}
  {task_id}
  existing_examples={existing_examples_for_dialog}
  allow_documents={true}
  on:submit={handle_example_submit}
  on:request_documents={handle_request_documents}
/>

<AddDocumentsDialog
  bind:this={add_documents_dialog}
  max_files={remaining_doc_slots}
  on:add={handle_documents_added}
/>

<SeeAllDialog bind:this={see_all_dialog} />
