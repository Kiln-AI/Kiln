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
  import OptionList from "$lib/ui/option_list.svelte"
  import type { OptionListItem } from "$lib/ui/option_list_types"
  import UploadIcon from "$lib/ui/icons/upload_icon.svelte"
  import DocumentIcon from "$lib/ui/icons/document_icon.svelte"
  import DatabaseIcon from "$lib/ui/icons/database_icon.svelte"
  import EditIcon from "$lib/ui/icons/edit_icon.svelte"
  import CsvIcon from "$lib/ui/icons/csv_icon.svelte"

  // Plaintext tasks expose the document-based sources (upload + library);
  // structured tasks fall back to manual entry. Dataset and CSV are offered to
  // both. Empty sources show their own empty state when opened, so they're
  // always listed here.
  export let is_structured_task: boolean = false

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

  function select_source(id: string) {
    pick(id as SampleSource)
  }

  $: source_options = [
    ...(!is_structured_task
      ? [
          {
            id: "upload",
            name: "Upload Documents",
            description:
              "Add document files from your computer as example inputs.",
            icon: UploadIcon,
          },
          {
            id: "library",
            name: "Project Documents",
            description:
              "Reuse documents from this project's Document Library as example inputs.",
            icon: DocumentIcon,
          },
        ]
      : []),
    {
      id: "dataset",
      name: "Dataset",
      description: "Reuse real inputs from past runs in your Kiln dataset.",
      icon: DatabaseIcon,
    },
    {
      id: "csv",
      name: "CSV Import",
      description: "Bulk-add many example inputs at once from a CSV file.",
      icon: CsvIcon,
    },
    ...(is_structured_task
      ? [
          {
            id: "manual_structured",
            name: "Manual Entry",
            description:
              "Write an example input by hand, following your task's input schema.",
            icon: EditIcon,
          },
        ]
      : []),
  ] satisfies OptionListItem[]
</script>

<Dialog
  title="Choose an Input Source"
  sub_subtitle="Pick where your example inputs come from. You can add more later."
  bind:this={dialog}
  width="wide"
>
  <OptionList options={source_options} select_option={select_source} />
</Dialog>
