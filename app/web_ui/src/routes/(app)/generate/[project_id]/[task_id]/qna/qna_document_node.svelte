<script lang="ts">
  import TableButton from "../table_button.svelte"
  import InfoTooltip from "$lib/ui/info_tooltip.svelte"

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

  function delete_part(part_id: string) {
    document.parts = document.parts.filter((p) => p.id !== part_id)
    document = document
    triggerSave()
  }

  $: total_qa_pairs = document.parts.reduce(
    (total, part) => total + part.qa_pairs.length,
    0,
  )

  $: has_parts = document.parts.length > 0
</script>

<!-- Document Header Row -->
<tr class="bg-base-200 border-t-2 border-base-100">
  <td colspan="3" class="py-2" style="padding-left: {(depth - 1) * 25 + 20}px">
    <div class="font-medium flex flex-row pr-4 w-full">
      <div class="flex-1">
        {#if depth > 1}
          <span class="text-xs relative" style="top: -3px">⮑</span>
        {/if}
        {document.name}
        <span class="text-xs text-gray-500 font-normal">
          ({total_qa_pairs} pairs)
        </span>
        {#if !document.extracted}
          <span class="badge badge-warning badge-sm ml-2">Not Extracted</span>
        {/if}
        <span class="relative inline-block w-3 h-3">
          <div class="absolute top-[-3px] left-0">
            <InfoTooltip
              tooltip_text="This is a document. Q&A pairs will be generated from its content."
              position="bottom"
              no_pad={true}
            />
          </div>
        </span>
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
          <button>Regenerate Q&A</button>
        </li>
        <li>
          <button>Delete Document</button>
        </li>
      </ul>
    </div>
  </td>
</tr>

{#if !has_parts}
  <tr>
    <td colspan="4" style="padding-left: {depth * 25 + 20}px" class="py-2">
      <div class="text-sm text-gray-500 italic">No Q&A pairs generated yet</div>
    </td>
  </tr>
{:else}
  {#each document.parts as part, partIndex}
    {#if document.parts.length > 1}
      <!-- Part Header Row (only show if document has multiple parts) -->
      <tr class="bg-base-200 border-t border-base-100">
        <td colspan="3" class="py-2" style="padding-left: {depth * 25 + 20}px">
          <div class="font-medium flex flex-row pr-4 w-full">
            <div class="flex-1">
              <span class="text-xs relative" style="top: -3px">⮑</span>
              Part {partIndex + 1}
              <span class="text-xs text-gray-500 font-normal">
                ({part.qa_pairs.length} pairs)
              </span>
              <span class="relative inline-block w-3 h-3">
                <div class="absolute top-[-3px] left-0">
                  <InfoTooltip
                    tooltip_text="A part of the document. Preview: {part.text_preview.substring(
                      0,
                      60,
                    )}..."
                    position="bottom"
                    no_pad={true}
                  />
                </div>
              </span>
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
                <button on:click|stopPropagation={() => delete_part(part.id)}>
                  Delete Part
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
              {#if qa.answer && !qa.saved_id}
                <li>
                  <button>Remove Answer</button>
                </li>
              {/if}
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
