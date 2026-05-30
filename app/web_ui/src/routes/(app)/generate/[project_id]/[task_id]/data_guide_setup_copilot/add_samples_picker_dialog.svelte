<script lang="ts" context="module">
  export type SampleSource =
    | "upload"
    | "library"
    | "dataset"
    | "csv"
    | "manual_structured"
</script>

<script lang="ts">
  import { createEventDispatcher } from "svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import UploadIcon from "$lib/ui/icons/upload_icon.svelte"
  import FileIcon from "$lib/ui/icons/file_icon.svelte"
  import DatabaseIcon from "$lib/ui/icons/database_icon.svelte"
  import EditIcon from "$lib/ui/icons/edit_icon.svelte"
  import CsvIcon from "$lib/ui/icons/csv_icon.svelte"

  // Plaintext tasks expose the document-based sources; structured tasks fall
  // back to manual entry + existing run picker.
  export let is_structured_task: boolean = false
  // Hide the Document Library row when the project has nothing in its library
  // yet — the dialog inside would just say "no documents".
  export let library_has_docs: boolean = false
  export let dataset_has_runs: boolean = false

  let dialog: Dialog | null = null

  const dispatch = createEventDispatcher<{
    pick: { source: SampleSource }
  }>()

  export function show() {
    dialog?.show()
  }

  export function close() {
    dialog?.close()
  }

  function pick(source: SampleSource) {
    dialog?.close()
    dispatch("pick", { source })
  }
</script>

<Dialog
  title="Add Examples"
  sub_subtitle="Choose a source to get started. You'll be able to add more examples later."
  bind:this={dialog}
  width="wide"
>
  <div class="flex flex-col gap-2">
    {#if !is_structured_task}
      <button type="button" class="source-row" on:click={() => pick("upload")}>
        <div class="source-icon bg-blue-50 text-[#628BD9]">
          <UploadIcon />
        </div>
        <div class="source-body">
          <div class="source-title">Upload Documents</div>
          <div class="source-desc">Import documents from your computer.</div>
        </div>
        <span class="source-chev">›</span>
      </button>

      {#if library_has_docs}
        <button
          type="button"
          class="source-row"
          on:click={() => pick("library")}
        >
          <div class="source-icon bg-blue-50 text-[#628BD9]">
            <FileIcon kind="document" />
          </div>
          <div class="source-body">
            <div class="source-title">Document Library</div>
            <div class="source-desc">
              Pick from documents already uploaded to this project.
            </div>
          </div>
          <span class="source-chev">›</span>
        </button>
      {/if}
    {/if}

    {#if is_structured_task}
      <button
        type="button"
        class="source-row"
        on:click={() => pick("manual_structured")}
      >
        <div class="source-icon bg-blue-50 text-[#628BD9]">
          <EditIcon />
        </div>
        <div class="source-body">
          <div class="source-title">Manual Entry</div>
          <div class="source-desc">
            Write an example input by hand using your task's input schema.
          </div>
        </div>
        <span class="source-chev">›</span>
      </button>
    {/if}

    {#if dataset_has_runs}
      <button type="button" class="source-row" on:click={() => pick("dataset")}>
        <div class="source-icon bg-blue-50 text-[#628BD9]">
          <DatabaseIcon />
        </div>
        <div class="source-body">
          <div class="source-title">Dataset</div>
          <div class="source-desc">
            Pick examples already in your Kiln Dataset.
          </div>
        </div>
        <span class="source-chev">›</span>
      </button>
    {/if}

    {#if !is_structured_task}
      <button type="button" class="source-row" on:click={() => pick("csv")}>
        <div class="source-icon bg-blue-50 text-[#628BD9]">
          <CsvIcon />
        </div>
        <div class="source-body">
          <div class="source-title">CSV</div>
          <div class="source-desc">
            Import a CSV file to batch import examples.
          </div>
        </div>
        <span class="source-chev">›</span>
      </button>
    {/if}
  </div>
</Dialog>

<style>
  .source-row {
    width: 100%;
    display: flex;
    align-items: flex-start;
    gap: 14px;
    padding: 14px 16px;
    border-radius: 12px;
    border: 1px solid #ececec;
    background: #fff;
    text-align: left;
    transition:
      border-color 120ms,
      background-color 120ms;
  }
  .source-row:hover {
    border-color: rgba(65, 92, 245, 0.4);
    background: #fafbff;
  }
  .source-icon {
    width: 40px;
    height: 40px;
    border-radius: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    padding: 9px;
  }
  .source-icon :global(svg) {
    width: 100%;
    height: 100%;
    display: block;
  }
  .source-body {
    flex: 1;
    min-width: 0;
  }
  .source-title {
    font-size: 15px;
    font-weight: 600;
    color: #131517;
    line-height: 1.25;
  }
  .source-desc {
    font-size: 13px;
    color: #5a5a5a;
    margin-top: 3px;
    line-height: 1.35;
  }
  .source-chev {
    color: #bdbdbd;
    font-size: 24px;
    line-height: 1;
    margin-top: 8px;
    flex-shrink: 0;
    transition: color 120ms;
  }
  .source-row:hover .source-chev {
    color: #415cf5;
  }
</style>
