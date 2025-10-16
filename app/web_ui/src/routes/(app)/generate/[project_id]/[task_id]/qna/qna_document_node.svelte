<script lang="ts">
  import TableButton from "../table_button.svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import Output from "../../../../run/output.svelte"
  import { createEventDispatcher } from "svelte"
  import { max_available_step } from "./qna_ui_store"

  type QnAPair = {
    id: string
    question: string
    answer: string
    generated: boolean
    model_name?: string
    model_provider?: string
    saved_id: string | null
  }

  type QnADocPart = {
    id: string
    text_preview: string
    qa_pairs: QnAPair[]
  }

  type QnADocumentNode = {
    id: string
    name: string
    tags: string[]
    extracted: boolean
    parts: QnADocPart[]
  }

  export let document: QnADocumentNode
  export let triggerSave: () => void
  export let depth: number = 1

  let expandedQAPairs: Record<string, boolean> = {}
  const dispatch = createEventDispatcher()

  // we don't enable the part dialog until after the extraction step
  $: output_dialog_possible = $max_available_step > 2

  // Dialogs
  let part_output_dialog: Dialog | null = null
  let selected_part_text: string | null = null
  let document_parts_dialog: Dialog | null = null

  function toggleQAPairExpand(qaId: string) {
    expandedQAPairs[qaId] = !expandedQAPairs[qaId]
    expandedQAPairs = expandedQAPairs
  }

  function delete_qa_pair(part_id: string, qa_id: string) {
    const part = document.parts.find((p) => p.id === part_id)
    if (part) {
      part.qa_pairs = part.qa_pairs.filter((qa) => qa.id !== qa_id)
      document = document
      triggerSave()
    }
  }

  function remove_part(part_id: string) {
    document.parts = document.parts.filter((p) => p.id !== part_id)
    document = document
    triggerSave()
  }

  $: total_qa_pairs = document.parts.reduce(
    (total, part) => total + part.qa_pairs.length,
    0,
  )

  $: has_parts = document.parts.length > 0

  function open_part_dialog(part_text: string) {
    selected_part_text = part_text
    part_output_dialog?.show()
  }

  function open_document_parts_dialog() {
    document_parts_dialog?.show()
  }
</script>

<!-- Document Header Row -->
<tr class="bg-base-200 border-base-100">
  <td colspan="3" class="py-2" style="padding-left: {(depth - 1) * 25 + 20}px">
    <div class="font-medium flex flex-row pr-4 w-full">
      <div class="flex-1">
        {#if depth > 1}
          <span class="text-xs relative" style="top: -3px">⮑</span>
        {/if}
        <button
          on:click|stopPropagation={output_dialog_possible
            ? open_document_parts_dialog
            : null}
          class:cursor-pointer={output_dialog_possible}
          class:hover:underline={output_dialog_possible}
        >
          {document.name}
        </button>
        <span class="text-xs text-gray-500 font-normal">
          ({total_qa_pairs} pairs)
        </span>
        {#if $max_available_step > 2 && !document.extracted}
          <span class="badge badge-warning badge-sm ml-2">Not Extracted</span>
        {/if}
      </div>
    </div>
  </td>
  <td class="p-0">
    <div class="dropdown dropdown-end dropdown-hover">
      <TableButton />
      <!-- svelte-ignore a11y-no-noninteractive-tabindex -->
      <ul
        tabindex="0"
        class="dropdown-content menu bg-base-100 rounded-box z-[1] w-52 p-2 shadow"
      >
        <li>
          <button
            on:click|stopPropagation={() =>
              dispatch("generate_for_document", { document_id: document.id })}
          >
            Generate Q&A for Document
          </button>
        </li>
        <li>
          <button>Remove Document</button>
        </li>
      </ul>
    </div>
  </td>
</tr>

{#if $max_available_step > 2 && !has_parts}
  <tr>
    <td colspan="4" style="padding-left: {depth * 25 + 20}px" class="py-2">
      <div class="text-sm text-gray-500 italic">No Q&A pairs generated yet</div>
    </td>
  </tr>
{:else}
  {#each document.parts as part, partIndex}
    {#if document.parts.length > 1}
      <!-- Part Header Row (only show if document has multiple parts) -->
      <tr
        class="bg-base-200 border-t border-base-100"
        on:click={() =>
          output_dialog_possible ? open_part_dialog(part.text_preview) : null}
        class:cursor-pointer={output_dialog_possible}
        class:hover:underline={output_dialog_possible}
      >
        <td colspan="3" class="py-2" style="padding-left: {depth * 25 + 20}px">
          <div class="font-medium flex flex-row pr-4 w-full">
            <div class="flex-1">
              <span class="text-xs relative" style="top: -3px">⮑</span>
              Part {partIndex + 1}
            </div>
          </div>
        </td>
        <td class="p-0">
          <div class="dropdown dropdown-end dropdown-hover">
            <TableButton />
            <!-- svelte-ignore a11y-no-noninteractive-tabindex -->
            <ul
              tabindex="0"
              class="dropdown-content menu bg-base-100 rounded-box z-[1] w-52 p-2 shadow"
            >
              <li>
                <button on:click|stopPropagation={() => remove_part(part.id)}>
                  Remove Part
                </button>
              </li>
              <li>
                <button
                  on:click|stopPropagation={() =>
                    dispatch("generate_for_part", {
                      document_id: document.id,
                      part_id: part.id,
                    })}
                >
                  Generate Q&A for Part
                </button>
              </li>
            </ul>
          </div>
        </td>
      </tr>
    {/if}

    {#each part.qa_pairs as qa}
      <tr on:click={() => toggleQAPairExpand(qa.id)} class="cursor-pointer">
        <td
          style="padding-left: {(depth + (document.parts.length > 1 ? 1 : 0)) *
            25 +
            20}px"
          class="py-2"
        >
          {#if expandedQAPairs[qa.id]}
            <pre class="whitespace-pre-wrap">{qa.question}</pre>
          {:else}
            <div class="truncate w-0 min-w-full">{qa.question}</div>
          {/if}
        </td>
        <td class="py-2">
          {#if !qa.answer}
            Not Generated
          {:else if expandedQAPairs[qa.id]}
            <pre class="whitespace-pre-wrap">{qa.answer}</pre>
          {:else}
            <div class="truncate w-0 min-w-full">{qa.answer}</div>
          {/if}
        </td>
        <td class="py-2">
          {#if qa.saved_id}
            <a href={`#`} class="hover:underline">Saved</a>
          {:else if qa.answer}
            Unsaved
          {:else}
            No Answer
          {/if}
        </td>
        <td class="p-0">
          <div class="dropdown dropdown-end dropdown-hover">
            <TableButton />
            <!-- svelte-ignore a11y-no-noninteractive-tabindex -->
            <ul
              tabindex="0"
              class="dropdown-content menu bg-base-100 rounded-box z-[1] w-52 p-2 shadow"
            >
              <li>
                <button
                  on:click|stopPropagation={() =>
                    delete_qa_pair(part.id, qa.id)}
                >
                  Remove Q&A Pair
                </button>
              </li>
              {#if qa.saved_id}
                <li>
                  <button>View in Dataset</button>
                </li>
              {/if}
            </ul>
          </div>
        </td>
      </tr>
    {/each}
  {/each}
{/if}

<!-- Single Part Output Dialog -->
<Dialog
  bind:this={part_output_dialog}
  title="Part Content"
  width="wide"
  action_buttons={[{ label: "Close", isCancel: true }]}
>
  {#if selected_part_text}
    <div class="mb-2 text-sm text-gray-500">
      The extractor produced the following output:
    </div>
    <Output raw_output={selected_part_text} />
  {:else}
    <div class="text-sm text-gray-500">No content.</div>
  {/if}
</Dialog>

<!-- All Parts for Document Dialog -->
<Dialog
  bind:this={document_parts_dialog}
  title="Document Parts"
  width="wide"
  action_buttons={[{ label: "Close", isCancel: true }]}
>
  {#if document.parts.length === 0}
    <div class="text-sm text-gray-500">No parts available.</div>
  {:else}
    <div class="space-y-6">
      {#each document.parts as part, idx}
        <div>
          <div class="mb-2 text-sm text-gray-500">Part {idx + 1}</div>
          <Output raw_output={part.text_preview} />
        </div>
      {/each}
    </div>
  {/if}
</Dialog>
