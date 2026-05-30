<script lang="ts" context="module">
  export type CsvImportRow = {
    text: string
  }
</script>

<script lang="ts">
  import { createEventDispatcher } from "svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import UploadIcon from "$lib/ui/icons/upload_icon.svelte"
  import { MAX_EXAMPLE_LENGTH } from "./input_examples_uploader.svelte"

  // -1 = no limit; otherwise caps the number of rows the parent will accept.
  export let max_rows: number = -1

  let dialog: Dialog | null = null
  let file_input: HTMLInputElement
  let drag_over = false
  let parsed_rows: string[] = []
  let parse_error: string | null = null
  let parse_warning: string | null = null
  let selected_file_name: string | null = null

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

  // Parse a single CSV line accounting for double-quoted fields. We only ever
  // read the first column, so the algorithm only needs to find the end of
  // that column.
  function first_csv_column(line: string): string {
    if (line.length === 0) return ""
    if (line[0] === '"') {
      let i = 1
      let result = ""
      while (i < line.length) {
        const ch = line[i]
        if (ch === '"') {
          if (i + 1 < line.length && line[i + 1] === '"') {
            result += '"'
            i += 2
          } else {
            return result
          }
        } else {
          result += ch
          i++
        }
      }
      return result
    }
    const comma = line.indexOf(",")
    return comma === -1 ? line : line.slice(0, comma)
  }

  async function process_file(file: File) {
    parse_error = null
    parse_warning = null
    parsed_rows = []
    selected_file_name = file.name
    try {
      const text = await file.text()
      // Normalize line endings; ignore blank lines.
      const lines = text
        .replace(/\r\n?/g, "\n")
        .split("\n")
        .map((l) => l)
        .filter((l) => l.trim().length > 0)
      if (lines.length === 0) {
        parse_error = `${selected_file_name} is empty.`
        return
      }
      // Treat the first line as a header iff it is literally "input"
      // (case-insensitive). Otherwise treat every line as data.
      const first_col_header = first_csv_column(lines[0]).trim().toLowerCase()
      const data_lines = first_col_header === "input" ? lines.slice(1) : lines
      let rows = data_lines
        .map(first_csv_column)
        .map((s) => s.trim())
        .filter((s) => s.length > 0)
      const warnings: string[] = []
      // Drop rows over the per-example character limit — they'd be blocked at
      // analyze time anyway, so skip them here with a heads-up.
      const within_length = rows.filter((r) => r.length <= MAX_EXAMPLE_LENGTH)
      const too_long = rows.length - within_length.length
      if (too_long > 0) {
        warnings.push(
          `${too_long} row${too_long === 1 ? "" : "s"} over the ${MAX_EXAMPLE_LENGTH.toLocaleString()} character limit will be skipped.`,
        )
      }
      rows = within_length
      if (max_rows >= 0 && rows.length > max_rows) {
        warnings.push(
          `${rows.length - max_rows} row${
            rows.length - max_rows === 1 ? "" : "s"
          } over the entry limit will be skipped.`,
        )
        rows = rows.slice(0, max_rows)
      }
      if (rows.length === 0) {
        parse_error = "No non-empty rows found in the first column."
        return
      }
      parse_warning = warnings.length > 0 ? warnings.join(" ") : null
      parsed_rows = rows
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
  sub_subtitle="Upload a CSV to add each row as an example input. The CSV must contain a single column, with one input per row. Do not include a header row."
  action_buttons={[
    {
      label:
        parsed_rows.length > 1
          ? `Import ${parsed_rows.length} Example${parsed_rows.length === 1 ? "" : "s"}`
          : "Import",
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
