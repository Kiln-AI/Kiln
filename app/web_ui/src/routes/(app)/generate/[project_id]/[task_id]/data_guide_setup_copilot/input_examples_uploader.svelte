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
  // True while a Continue-triggered extraction run is live; forwarded to the
  // See All dialog so pending document rows read "Extracting…".
  export let extraction_in_progress: boolean = false

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
  }>()

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
  // Hard total cap: the example count can't exceed MAX_TOTAL_ENTRIES. Each add
  // is truncated to the remaining room (see append_with_cap), so once at the
  // cap we disable adding more.
  $: at_cap = entries.length >= MAX_TOTAL_ENTRIES
  // Set when the most recent add dropped items to stay under the cap. Cleared
  // on a non-truncating add or on removal.
  let truncation_notice = ""
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

  // Append `incoming` up to the room left under MAX_TOTAL_ENTRIES. Callers pass
  // entries already in priority order — most-recent-first for tag picks, file
  // order for CSV/uploads — so the survivors are the ones we want to keep.
  // `kept_label` ("most recent" / "first") and the nouns shape the user notice
  // when some are dropped. Truncating here (rather than at analyze time) means
  // the drop is visible the moment it happens.
  function append_with_cap(
    incoming: InputExampleEntry[],
    noun_singular: string,
    noun_plural: string,
    kept_label: string,
  ) {
    const remaining = Math.max(0, MAX_TOTAL_ENTRIES - entries.length)
    const accepted = incoming.slice(0, remaining)
    const dropped = incoming.length - accepted.length
    if (accepted.length > 0) {
      entries = [...entries, ...accepted]
      emit_change()
    }
    if (dropped === 0) {
      truncation_notice = ""
      return
    }
    const noun = dropped === 1 ? noun_singular : noun_plural
    const verb = dropped === 1 ? "was" : "were"
    truncation_notice =
      accepted.length === 0
        ? `You're at the ${MAX_TOTAL_ENTRIES}-example limit — ${dropped} ${noun} ${verb} not added. Remove some to add more.`
        : `Added the ${kept_label} ${accepted.length} — ${dropped} ${noun} ${verb} skipped to stay under the ${MAX_TOTAL_ENTRIES}-example limit.`
  }

  function remove_entry(index: number) {
    entries = entries.filter((_, i) => i !== index)
    truncation_notice = ""
    emit_change()
  }

  // --- Source picker dispatch ----------------------------------------------

  function open_source_picker() {
    // Guards every entry point (main button, empty state, See All "add") once
    // the cap is reached.
    if (at_cap) return
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
  // DATA_GUIDE_DOC_TAG). Turn the created docs into document entries with
  // empty text; extraction runs later from Continue.
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
    append_with_cap(new_entries, "document", "documents", "first")
    library_has_docs = true
  }

  // --- Source dialog handlers -----------------------------------------------

  // Add the picked library docs as (text-less) document entries. They're not
  // tagged — the Continue-step extraction scopes by document id. Their text is
  // hydrated when that extraction completes.
  function handle_library_add(event: CustomEvent<{ picks: LibraryPick[] }>) {
    const new_entries: InputExampleEntry[] = event.detail.picks.map((p) => ({
      source: "document",
      label: p.label,
      text: "",
      document_id: p.document_id,
    }))
    // Picks arrive newest-first (the library list is sorted by created_at desc),
    // so truncation keeps the most recent.
    append_with_cap(new_entries, "document", "documents", "most recent")
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
    // Runs arrive newest-first (dataset sorted by created_at desc), so
    // truncation keeps the most recent.
    append_with_cap(new_entries, "run", "runs", "most recent")
  }

  function handle_csv_import(event: CustomEvent<{ rows: CsvImportRow[] }>) {
    const new_entries: InputExampleEntry[] = event.detail.rows.map(
      (r, idx) => ({
        source: "manual",
        label: `CSV row ${manual_count + idx + 1}`,
        text: r.text,
      }),
    )
    append_with_cap(new_entries, "row", "rows", "first")
  }

  function handle_structured_add(event: CustomEvent<{ text: string }>) {
    append_with_cap(
      [
        {
          source: "manual",
          label: `Manual ${manual_count + 1}`,
          text: event.detail.text,
        },
      ],
      "example",
      "examples",
      "first",
    )
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
          <span class="font-semibold text-[#131517] tabular-nums"
            >{entries.length}
            {entries.length === 1 ? "example" : "examples"}</span
          >
          will be analyzed to draft your guide.{#if at_cap}
            <span class="text-[#131517]">
              You're at the {MAX_TOTAL_ENTRIES}-example limit.</span
            >
          {/if}
        </div>
        {#if truncation_notice}
          <div class="text-sm text-warning mt-1">
            {truncation_notice}
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
          disabled={at_cap}
          title={at_cap
            ? `You're at the ${MAX_TOTAL_ENTRIES}-example limit. Remove some to add more.`
            : undefined}
        >
          Add Examples
        </button>
      </div>
    </div>

    <!-- Structured tasks hide the Documents tile, leaving two buckets — drop to
         a 2-col grid so there's no empty third column (and the header buttons
         line up over the second bucket). -->
    <div
      class="grid grid-cols-1 sm:grid-cols-2 gap-3 {is_structured_task
        ? ''
        : 'lg:grid-cols-3'}"
    >
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
        <div class="tile-label">
          {is_structured_task ? "Manual Entries" : "Imported Examples"}
        </div>
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
  subtitle="Add files to use as example inputs for your data guide."
  max_files={Math.max(0, MAX_TOTAL_ENTRIES - entries.length)}
  onUploadCompleted={handle_documents_uploaded}
/>

<AllSamplesDialog
  bind:this={all_samples_dialog}
  {project_id}
  {task_id}
  {is_structured_task}
  {entries}
  {extraction_in_progress}
  initial_filter={initial_all_samples_filter}
  on:remove={handle_all_samples_remove}
  on:add={open_source_picker}
/>

<!-- No auto_tags: picking an existing library doc must not tag it. Extraction
     at Continue is scoped by document id, not by tag. -->
<SelectFromLibraryDialog
  bind:this={select_from_library_dialog}
  {project_id}
  {existing_document_ids}
  extract_after_pick={false}
  on:add={handle_library_add}
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
