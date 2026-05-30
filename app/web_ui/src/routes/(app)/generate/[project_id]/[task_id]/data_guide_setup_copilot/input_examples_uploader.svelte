<script lang="ts" context="module">
  // What goes to the analyze endpoint is just `text`. Document entries
  // additionally carry `document_id` so the page can resolve missing
  // extractions before send, and an optional `extraction_id` once an
  // extraction has been picked.
  export type InputExampleEntry = {
    source: "document" | "manual" | "task_run"
    label: string
    text: string
    document_id?: string
    extraction_id?: string
    task_run_id?: string
  }

  // Soft cap on examples sent to analyze. Mirrors the backend's
  // DRAFT_INPUT_DATA_GUIDE_MAX_EXAMPLES. Not enforced at add time — users can
  // add more freely; the analyze step takes the first MAX_TOTAL_ENTRIES and
  // warns when over.
  export const MAX_TOTAL_ENTRIES = 200
  // Per-example character ceiling. Mirrors the backend's
  // DRAFT_INPUT_DATA_GUIDE_MAX_EXAMPLE_LENGTH — each example becomes one
  // summarize LLM call. Unlike the count cap, this is a hard reject: the
  // analyze step blocks before sending if any example exceeds it.
  export const MAX_EXAMPLE_LENGTH = 200_000
</script>

<script lang="ts">
  import { createEventDispatcher, onMount } from "svelte"
  import type { Task, BulkCreateDocumentsResponse, TaskRun } from "$lib/types"
  import { client } from "$lib/api_client"
  import SelectFromLibraryDialog, {
    type LibraryPick,
  } from "./select_from_library_dialog.svelte"
  import ExistingRunPickerDialog from "./existing_run_picker_dialog.svelte"
  import ImportCsvDialog, {
    type CsvImportRow,
  } from "./import_csv_dialog.svelte"
  import AddManualStructuredDialog from "./add_manual_structured_dialog.svelte"
  import AddSamplesPickerDialog, {
    type SampleSource,
  } from "./add_samples_picker_dialog.svelte"
  import AllSamplesDialog from "./all_samples_dialog.svelte"
  import UploadFileDialog from "../../../../docs/library/[project_id]/upload_file_dialog.svelte"
  import Intro from "$lib/ui/intro.svelte"
  import CopyDocumentsIcon from "$lib/ui/icons/copy_documents_icon.svelte"
  import FileIcon from "$lib/ui/icons/file_icon.svelte"
  import DatabaseIcon from "$lib/ui/icons/database_icon.svelte"
  import EditIcon from "$lib/ui/icons/edit_icon.svelte"

  const DOCS_LINK = "https://docs.kiln.tech/docs/synthetic-data-generation"

  // Tag applied to documents uploaded to the Document Library from this page.
  // Persists so users can find / curate them later under that tag.
  const DATA_GUIDE_DOC_TAG = "data_guide_example"

  export let project_id: string
  export let task_id: string
  export let task: Task | null = null
  export let entries: InputExampleEntry[] = []

  let add_samples_picker: AddSamplesPickerDialog
  let all_samples_dialog: AllSamplesDialog
  let upload_file_dialog: UploadFileDialog
  let select_from_library_dialog: SelectFromLibraryDialog
  let existing_run_picker_dialog: ExistingRunPickerDialog
  let import_csv_dialog: ImportCsvDialog
  let add_manual_structured_dialog: AddManualStructuredDialog

  // Whether the project has any documents in its library yet. Drives the
  // "Document Library" row visibility in the source picker — no point offering
  // it when nothing's there.
  let library_has_docs: boolean = false

  let dataset_has_runs: boolean = false

  const dispatch = createEventDispatcher<{
    change: { entries: InputExampleEntry[] }
    extraction_complete: { extractor_config_id: string; error_count: number }
  }>()

  function forward_extraction_complete(
    event: CustomEvent<{ extractor_config_id: string; error_count: number }>,
  ) {
    dispatch("extraction_complete", event.detail)
  }

  // Plaintext tasks (no input JSON schema) lean on document uploads as the
  // primary input source. Structured-input tasks expose a structured manual
  // entry path + existing-run picker instead.
  $: is_structured_task = !!task?.input_json_schema

  $: doc_count = entries.filter((e) => e.source === "document").length
  $: run_count = entries.filter((e) => e.source === "task_run").length
  $: manual_count = entries.filter((e) => e.source === "manual").length
  $: existing_document_ids = entries
    .map((e) => e.document_id)
    .filter((id): id is string => !!id)
  $: existing_task_run_ids = entries
    .map((e) => e.task_run_id)
    .filter((id): id is string => !!id)
  // Soft count cap: only the first MAX_TOTAL_ENTRIES are analyzed. We don't
  // block adding more; this just drives a heads-up notice.
  $: over_count = entries.length > MAX_TOTAL_ENTRIES
  // Examples whose resolved text exceeds the per-example limit. Computed
  // reactively so document entries are flagged as soon as extraction populates
  // their text — not just at Continue. The analyze step hard-blocks on these.
  $: over_length_count = entries.filter(
    (e) => !!e.text && e.text.length > MAX_EXAMPLE_LENGTH,
  ).length

  onMount(() => {
    refresh_library_has_docs()
    refresh_dataset_has_runs()
  })

  async function refresh_library_has_docs() {
    try {
      const { data } = await client.GET(
        "/api/projects/{project_id}/documents",
        { params: { path: { project_id } } },
      )
      library_has_docs = !!data && data.length > 0
    } catch {
      library_has_docs = false
    }
  }

  async function refresh_dataset_has_runs() {
    try {
      const { data } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}/runs",
        { params: { path: { project_id, task_id } } },
      )
      dataset_has_runs = !!data && data.length > 0
    } catch {
      dataset_has_runs = false
    }
  }

  function emit_change() {
    dispatch("change", { entries })
  }

  function remove_entry(index: number) {
    entries = entries.filter((_, i) => i !== index)
    emit_change()
  }

  // --- Source picker dispatch ----------------------------------------------

  function open_source_picker() {
    add_samples_picker?.show()
  }

  function handle_source_pick(event: CustomEvent<{ source: SampleSource }>) {
    const s = event.detail.source
    if (s === "upload") {
      upload_file_dialog?.show()
    } else if (s === "library") {
      select_from_library_dialog?.show()
    } else if (s === "dataset") {
      existing_run_picker_dialog?.show()
    } else if (s === "csv") {
      import_csv_dialog?.show()
    } else if (s === "manual_structured") {
      add_manual_structured_dialog?.show()
    }
  }

  // Uploads run inside the reused upload dialog (it tags files with
  // DATA_GUIDE_DOC_TAG). Turn the created docs into document entries; the upload
  // dialog then runs the inline extraction step before it closes.
  function handle_documents_uploaded(
    result: BulkCreateDocumentsResponse | null,
  ) {
    if (!result) return
    const created = result.created_documents.filter(
      (d): d is typeof d & { id: string } => !!d.id,
    )
    if (created.length === 0) return
    const new_entries: InputExampleEntry[] = created.map((d) => ({
      source: "document",
      label: d.friendly_name,
      text: "",
      document_id: d.id,
    }))
    entries = [...entries, ...new_entries]
    emit_change()
    library_has_docs = true
  }

  // --- Source dialog handlers -----------------------------------------------

  // The library dialog tags the picks and runs the inline extraction step
  // itself; here we just add them as (text-less) document entries. Their text is
  // hydrated when the dialog reports extraction_complete.
  function handle_library_add(event: CustomEvent<{ picks: LibraryPick[] }>) {
    const new_entries: InputExampleEntry[] = event.detail.picks.map((p) => ({
      source: "document",
      label: p.label,
      text: "",
      document_id: p.document_id,
    }))
    entries = [...entries, ...new_entries]
    emit_change()
  }

  function handle_existing_runs_add(event: CustomEvent<{ runs: TaskRun[] }>) {
    const new_entries: InputExampleEntry[] = event.detail.runs.map((run) => {
      const id = run.id ?? undefined
      return {
        source: "task_run",
        label: id ? `Existing run · ${id.slice(0, 6)}` : "Existing run",
        text: run.input ?? "",
        task_run_id: id,
      }
    })
    entries = [...entries, ...new_entries]
    emit_change()
  }

  function handle_csv_import(event: CustomEvent<{ rows: CsvImportRow[] }>) {
    const new_entries: InputExampleEntry[] = event.detail.rows.map(
      (r, idx) => ({
        source: "manual",
        label: `CSV row ${manual_count + idx + 1}`,
        text: r.text,
      }),
    )
    entries = [...entries, ...new_entries]
    emit_change()
  }

  function handle_structured_add(event: CustomEvent<{ text: string }>) {
    entries = [
      ...entries,
      {
        source: "manual",
        label: `Manual ${manual_count + 1}`,
        text: event.detail.text,
      },
    ]
    emit_change()
  }

  // --- All Samples handlers ------------------------------------------------

  type FilterKey = "all" | "document" | "task_run" | "manual"
  let initial_all_samples_filter: FilterKey = "all"

  function open_all_samples(filter: FilterKey = "all") {
    initial_all_samples_filter = filter
    all_samples_dialog?.show()
  }

  function handle_all_samples_remove(event: CustomEvent<{ index: number }>) {
    remove_entry(event.detail.index)
  }
</script>

<div>
  {#if entries.length === 0}
    <!-- Intro / empty state ---------------------------------------------- -->
    <div class="flex items-center justify-center py-12 sm:py-16">
      <Intro
        title="Start by Adding Examples"
        description_markdown={"Show Kiln what good inputs look like. Add real or representative examples of the inputs your task will receive.\nKiln Pro uses them to draft a Data Guide you can review and refine. More examples lead to a better guide."}
        action_buttons={[
          {
            label: "Add Examples",
            is_primary: true,
            onClick: open_source_picker,
          },
          {
            label: "Docs & Guide",
            href: DOCS_LINK,
            new_tab: true,
            is_primary: false,
          },
        ]}
      >
        <div slot="icon" class="h-12 w-12">
          <CopyDocumentsIcon />
        </div>
      </Intro>
    </div>
  {:else}
    <!-- Filled summary ---------------------------------------------------- -->
    <div class="flex flex-wrap items-end justify-between gap-3 mb-5">
      <div>
        <div class="text-xl font-bold text-[#131517] tracking-tight">
          Examples
        </div>
        <div class="text-sm text-[#5a5a5a] mt-1">
          {#if over_count}
            <span class="font-semibold text-[#131517] tabular-nums"
              >{MAX_TOTAL_ENTRIES}</span
            >
            of
            <span class="tabular-nums">{entries.length}</span>
            examples will be analyzed to draft your guide.
          {:else}
            <span class="font-semibold text-[#131517] tabular-nums"
              >{entries.length}
              {entries.length === 1 ? "example" : "examples"}</span
            >
            will be analyzed to draft your guide.
          {/if}
        </div>
        {#if over_count}
          <div class="text-sm text-[#5a5a5a] mt-1">
            You've added more than {MAX_TOTAL_ENTRIES} examples — only the first
            {MAX_TOTAL_ENTRIES} will be analyzed.
          </div>
        {/if}
        {#if over_length_count > 0}
          <div class="text-sm text-error mt-1">
            {over_length_count}
            {over_length_count === 1 ? "example exceeds" : "examples exceed"}
            the {MAX_EXAMPLE_LENGTH.toLocaleString()} character limit. Open
            <button
              type="button"
              class="link"
              on:click={() => open_all_samples("all")}>See All</button
            >
            to remove or shorten
            {over_length_count === 1 ? "it" : "them"} before continuing.
          </div>
        {/if}
      </div>
      <div class="flex items-center gap-2">
        <button
          type="button"
          class="btn btn-sm btn-outline"
          on:click={() => open_all_samples("all")}
        >
          See All
        </button>
        <button
          type="button"
          class="btn btn-sm btn-primary btn-outline gap-1.5"
          on:click={open_source_picker}
        >
          Add Examples
        </button>
      </div>
    </div>

    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
      {#if !is_structured_task}
        <button
          type="button"
          class="stat-tile"
          on:click={() => open_all_samples("document")}
          disabled={doc_count === 0}
        >
          <div class="tile-head">
            <div class="tile-icon bg-blue-50 text-[#628BD9]">
              <FileIcon kind="document" />
            </div>
          </div>
          <div class="tile-count">{doc_count}</div>
          <div class="tile-label">
            {doc_count === 1 ? "Document" : "Documents"}
          </div>
        </button>
      {/if}

      <button
        type="button"
        class="stat-tile"
        on:click={() => open_all_samples("task_run")}
        disabled={run_count === 0}
      >
        <div class="tile-head">
          <div class="tile-icon bg-blue-50 text-[#628BD9]">
            <DatabaseIcon />
          </div>
        </div>
        <div class="tile-count">{run_count}</div>
        <div class="tile-label">From Dataset</div>
      </button>

      <button
        type="button"
        class="stat-tile"
        on:click={() => open_all_samples("manual")}
        disabled={manual_count === 0}
      >
        <div class="tile-head">
          <div class="tile-icon bg-blue-50 text-[#628BD9]">
            <EditIcon />
          </div>
        </div>
        <div class="tile-count">{manual_count}</div>
        <div class="tile-label">Imported Examples</div>
      </button>
    </div>
  {/if}
</div>

<AddSamplesPickerDialog
  bind:this={add_samples_picker}
  {is_structured_task}
  {library_has_docs}
  {dataset_has_runs}
  on:pick={handle_source_pick}
/>

<UploadFileDialog
  bind:this={upload_file_dialog}
  auto_tags={[DATA_GUIDE_DOC_TAG]}
  close_on_success={true}
  extract_after_upload={true}
  extract_tags={[DATA_GUIDE_DOC_TAG]}
  subtitle="Add files to use as example inputs for your data guide."
  onUploadCompleted={handle_documents_uploaded}
  onExtractionComplete={(extractor_config_id, error_count) =>
    dispatch("extraction_complete", { extractor_config_id, error_count })}
/>

<AllSamplesDialog
  bind:this={all_samples_dialog}
  {project_id}
  {task_id}
  {entries}
  initial_filter={initial_all_samples_filter}
  on:remove={handle_all_samples_remove}
/>

<SelectFromLibraryDialog
  bind:this={select_from_library_dialog}
  {project_id}
  {existing_document_ids}
  auto_tags={[DATA_GUIDE_DOC_TAG]}
  on:add={handle_library_add}
  on:extraction_complete={forward_extraction_complete}
/>

<ExistingRunPickerDialog
  bind:this={existing_run_picker_dialog}
  {project_id}
  {task_id}
  {existing_task_run_ids}
  on:add={handle_existing_runs_add}
/>

<ImportCsvDialog bind:this={import_csv_dialog} on:add={handle_csv_import} />

{#if task?.input_json_schema}
  <AddManualStructuredDialog
    bind:this={add_manual_structured_dialog}
    input_json_schema={task.input_json_schema}
    on:add={handle_structured_add}
  />
{/if}

<style>
  .stat-tile {
    text-align: left;
    border-radius: 16px;
    border: 1px solid #bebebe; /* base-300, matching the optimize cards */
    background: #fff;
    padding: 20px 24px;
    transition: all 200ms;
    display: flex;
    flex-direction: column;
  }
  .stat-tile:hover:not(:disabled) {
    /* primary/50 + lift + shadow, matching the optimize tab cards */
    border-color: rgba(65, 92, 245, 0.5);
    box-shadow:
      0 10px 15px -3px rgb(0 0 0 / 0.1),
      0 4px 6px -4px rgb(0 0 0 / 0.1);
    transform: translateY(-2px);
  }
  .stat-tile:disabled {
    /* scaled-down base-300 so inactive tiles read lighter */
    border-color: #e0e0e0;
    opacity: 0.65;
    cursor: default;
  }
  .tile-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 16px;
  }
  .tile-icon {
    width: 40px;
    height: 40px;
    border-radius: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .tile-icon :global(svg) {
    width: 19px;
    height: 19px;
    display: block;
  }
  .tile-count {
    font-size: 34px;
    font-weight: 700;
    color: #131517;
    line-height: 1;
    font-variant-numeric: tabular-nums;
  }
  .tile-label {
    font-size: 15px;
    color: #131517;
    margin-top: 8px;
    font-weight: 500;
  }
</style>
