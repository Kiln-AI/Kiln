<script lang="ts" context="module">
  export type CsvImportRow = {
    text: string
  }
</script>

<script lang="ts">
  import { createEventDispatcher } from "svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import UploadIcon from "$lib/ui/icons/upload_icon.svelte"
  import { client } from "$lib/api_client"

  export let project_id: string
  export let task_id: string
  // When set, the task has a structured input schema. This only drives the
  // dialog's copy and accepted file types — the backend reads the schema off
  // the task and decides how to parse (single-column CSV vs one JSON per line).
  export let input_json_schema: string | null = null

  let dialog: Dialog | null = null
  let file_input: HTMLInputElement
  let drag_over = false
  let parsed_rows: string[] = []
  let parse_error: string | null = null
  let parse_warning: string | null = null
  let selected_file_name: string | null = null

  $: is_structured = !!input_json_schema
  $: dialog_subtitle = is_structured
    ? "Upload a single-column CSV where each row is a JSON object matching this task's input schema. Export from a spreadsheet so the JSON's commas and quotes are escaped."
    : "Upload a CSV to add each row as an example input. The CSV must contain a single column, with one input per row. Do not include a header row."

  const dispatch = createEventDispatcher<{
    add: { rows: CsvImportRow[] }
  }>()

  export function show() {
    parsed_rows = []
    parse_error = null
    parse_warning = null
    selected_file_name = null
    dialog?.show()
  }

  function close() {
    dialog?.close()
    return true
  }

  // Parsing + validation happens server-side: the backend reads the schema off
  // the task and parses a single-column CSV (plaintext) or one JSON object per
  // line (structured) with the stdlib csv / json parsers, returning the rows
  // plus any whole-file error or partial-skip warning.
  async function process_file(file: File) {
    parse_error = null
    parse_warning = null
    parsed_rows = []
    selected_file_name = file.name
    const form_data = new FormData()
    form_data.append("file", file)
    try {
      const { data, error } = await client.POST(
        "/api/projects/{project_id}/tasks/{task_id}/copilot/parse_import_file",
        {
          params: { path: { project_id, task_id } },
          // Multipart uploads aren't typed by openapi-typescript; cast the
          // FormData body as the dataset uploader does.
          body: form_data as unknown as { file: string },
        },
      )
      if (error) {
        parse_error =
          (error as { message?: string })?.message ??
          "Couldn't read that file. Please try again."
        return
      }
      if (!data) {
        parse_error = "Couldn't read that file. Please try again."
        return
      }
      parse_error = data.error ?? null
      parse_warning = data.warning ?? null
      parsed_rows = data.rows
    } catch (e) {
      parse_error = e instanceof Error ? e.message : String(e)
    }
  }

  function handle_file_select(event: Event) {
    const input = event.target as HTMLInputElement
    if (input.files && input.files[0]) {
      process_file(input.files[0])
    }
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
    const file = event.dataTransfer?.files?.[0]
    if (file) process_file(file)
  }

  function open_file_dialog() {
    file_input?.click()
  }

  async function handle_add(): Promise<boolean> {
    if (parsed_rows.length === 0) return false
    dispatch("add", { rows: parsed_rows.map((text) => ({ text })) })
    close()
    return true
  }
</script>

<Dialog
  bind:this={dialog}
  title="Import from CSV"
  sub_subtitle={dialog_subtitle}
  action_buttons={[
    {
      label: "Import",
      asyncAction: () => handle_add(),
      disabled: parsed_rows.length === 0,
      isPrimary: true,
    },
  ]}
>
  <div class="flex flex-col gap-4 text-sm">
    <div
      class="border-2 border-dashed rounded-lg p-6 text-center transition-colors cursor-pointer {drag_over
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
        <p class="text-gray-500">
          {selected_file_name
            ? selected_file_name
            : "Drop a CSV here or click to select"}
        </p>
      </div>
    </div>

    <input
      bind:this={file_input}
      type="file"
      accept=".csv"
      class="hidden"
      on:change={handle_file_select}
    />

    {#if parse_error}
      <div class="text-error text-right">{parse_error}</div>
    {/if}
    {#if parse_warning}
      <div class="text-warning text-xs text-right">{parse_warning}</div>
    {/if}

    {#if parsed_rows.length > 0}
      <div>
        <div class="font-medium mb-1">
          Preview ({parsed_rows.length} example{parsed_rows.length === 1
            ? ""
            : "s"})
        </div>
        <div class="rounded border max-h-48 overflow-y-auto">
          <table class="table table-fixed text-xs">
            <tbody>
              {#each parsed_rows as row, i}
                <tr>
                  <td class="py-1 text-gray-400" style="width: 40px">{i + 1}</td
                  >
                  <td class="py-1 truncate" title={row}>{row}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      </div>
    {/if}
  </div>
</Dialog>
