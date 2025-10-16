<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import { client } from "$lib/api_client"
  import { base_url } from "$lib/api_client"
  import { onMount } from "svelte"
  import { page } from "$app/stores"
  import { indexedDBStore } from "$lib/stores/index_db_store"
  import { writable, type Writable } from "svelte/store"
  import Dialog from "$lib/ui/dialog.svelte"
  import InfoTooltip from "$lib/ui/info_tooltip.svelte"
  import type { ModelProviderName, RunConfigProperties } from "$lib/types"
  import SelectDocumentsModal from "./select_documents_dialog.svelte"
  import ExtractionModal from "./extraction_dialog.svelte"
  import GenerateQnaModal from "./generate_qna_dialog.svelte"
  import QnaDocumentNode from "./qna_document_node.svelte"
  import FileIcon from "$lib/ui/icons/file_icon.svelte"
  import QnaGenIntro from "./qna_gen_intro.svelte"

  $: project_id = $page.params.project_id
  $: task_id = $page.params.task_id

  const DEFAULT_QNA_GUIDANCE = `You are generating question-answer pairs from document content to create a dataset for training and evaluating AI systems.

For each document part:
1. Generate clear, specific questions that can be answered using the content
2. Provide accurate, complete answers based solely on the document content
3. Vary question types (factual, conceptual, procedural, etc.)
4. Ensure questions are self-contained and answerable

Focus on:
- Key concepts and important information
- Practical applications and examples
- Definitions and explanations
- Relationships between ideas

Avoid:
- Yes/no questions unless they lead to explanatory follow-up
- Questions requiring information not in the document
- Ambiguous or unclear phrasing`

  // Data types
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

  type QnASession = {
    selected_tags: string[]
    extractor_id: string | null
    extraction_complete: boolean
    generation_config: {
      pairs_per_part: number
      part_size: "small" | "medium" | "large" | "full"
      guidance: string
    }
    documents: QnADocumentNode[]
    splits: Record<string, number>
  }

  // Session state
  let saved_state: Writable<QnASession> = writable({
    selected_tags: [],
    extractor_id: null,
    extraction_complete: false,
    generation_config: {
      pairs_per_part: 5,
      part_size: "medium" as const,
      guidance: DEFAULT_QNA_GUIDANCE,
    },
    documents: [],
    splits: {},
  })

  // UI state
  type StepNumber = 1 | 2 | 3 | 4
  const step_numbers: StepNumber[] = [1, 2, 3, 4]
  let current_step: StepNumber = 1
  const step_names: Record<StepNumber, string> = {
    1: "Select Documents",
    2: "Extraction",
    3: "Generate Q&A",
    4: "Save Data",
  }
  const step_descriptions: Record<StepNumber, string> = {
    1: "Choose which documents to generate Q&A pairs from",
    2: "Extract text content from selected documents",
    3: "Generate question and answer pairs from extracted content",
    4: "Save generated Q&A pairs to dataset",
  }

  // Dialogs
  let clear_existing_state_dialog: Dialog | null = null
  let edit_splits_dialog: Dialog | null = null
  let generating_dialog: Dialog | null = null

  // Tag selection
  let available_tags: string[] = []

  // Splits editing
  let editable_splits: Array<{ tag: string; percent: number }> = []

  onMount(async () => {
    const qna_data_key = `qna_data_${project_id}_${task_id}`
    const { store, initialized } = indexedDBStore<QnASession>(qna_data_key, {
      selected_tags: [],
      extractor_id: null,
      extraction_complete: false,
      generation_config: {
        pairs_per_part: 5,
        part_size: "medium" as const,
        guidance: DEFAULT_QNA_GUIDANCE,
      },
      documents: [],
      splits: {},
    })
    await initialized
    saved_state = store

    // Show continue session dialog if there's existing data
    if ($saved_state.documents.length > 0) {
      clear_existing_state_dialog?.show()
    }

    await loadAvailableTags()
    update_current_step()
  })

  function update_current_step() {
    const has_qa_pairs = $saved_state.documents.some((doc) =>
      doc.parts.some((part: QnADocPart) => part.qa_pairs.length > 0),
    )
    if (has_qa_pairs) {
      set_current_step(4)
    } else if ($saved_state.extraction_complete) {
      set_current_step(3)
    } else if ($saved_state.documents.length > 0) {
      set_current_step(2)
    } else {
      set_current_step(1)
    }
  }

  function set_current_step(step: StepNumber) {
    current_step = step
  }

  function clear_all_state() {
    saved_state.update((s) => ({
      ...s,
      selected_tags: [],
      extractor_id: null,
      extraction_complete: false,
      generation_config: {
        pairs_per_part: 5,
        part_size: "medium" as const,
        guidance: DEFAULT_QNA_GUIDANCE,
      },
      documents: [],
      splits: {},
    }))
  }

  function clear_state_and_go_to_intro() {
    clear_all_state()
    window.location.href = `/generate/${project_id}/${task_id}`
    return true
  }

  async function loadAvailableTags() {
    try {
      const { data, error } = await client.GET(
        "/api/projects/{project_id}/documents/tags",
        {
          params: {
            path: {
              project_id,
            },
          },
        },
      )

      if (error) {
        throw error
      }

      available_tags = data || []
    } catch (e) {
      console.error("Error loading tags:", e)
      available_tags = []
    }
  }

  let current_dialog_type:
    | "select_documents"
    | "extraction"
    | "generate_qna"
    | null = null
  let show_select_documents_modal: Dialog | null = null
  let show_extraction_modal: Dialog | null = null
  let show_generate_qna_modal: Dialog | null = null

  function open_select_documents_modal() {
    current_dialog_type = "select_documents"
    show_select_documents_modal?.show()
  }

  function open_extraction_modal() {
    current_dialog_type = "extraction"
    show_extraction_modal?.show()
  }

  function open_generate_qna_modal() {
    current_dialog_type = "generate_qna"
    pending_generation_target = { type: "all" }
    show_generate_qna_modal?.show()
  }

  function handle_documents_added(event: CustomEvent) {
    const { documents, tags } = event.detail

    // Convert API documents to QnADocumentNode format
    const new_documents: QnADocumentNode[] = documents.map(
      (doc: { id: string; name: string; tags?: string[] }) => ({
        id: doc.id,
        name: doc.name,
        tags: doc.tags || [],
        extracted: false,
        parts: [],
      }),
    )

    saved_state.update((s) => ({
      ...s,
      documents: [...s.documents, ...new_documents],
      selected_tags: tags,
    }))

    triggerSaveUiState()
    set_current_step(2)
  }

  function handle_extraction_complete(
    event: CustomEvent<{ extractor_config_id: string }>,
  ) {
    const { extractor_config_id } = event.detail

    saved_state.update((s) => ({
      ...s,
      extractor_id: extractor_config_id,
      extraction_complete: true,
      documents: s.documents.map((doc) => ({
        ...doc,
        extracted: true,
      })),
    }))

    triggerSaveUiState()
    set_current_step(3)

    // Load extractions for this extractor and split into parts for UI
    void (async () => {
      try {
        const res = await fetch(
          `${base_url}/api/projects/${project_id}/extractor_configs/${extractor_config_id}/extractions`,
        )
        if (!res.ok)
          throw new Error(`Failed to fetch extractions: ${res.status}`)
        const data: Record<
          string,
          Array<{ output_content: string }>
        > = await res.json()

        // For each document in saved state, attach parts sliced to 1000 chars
        saved_state.update((s) => ({
          ...s,
          documents: s.documents.map((doc) => {
            const docExtractions = data[doc.id] || []
            const parts = docExtractions.flatMap((extraction) => {
              const text = extraction.output_content || ""
              const chunkSize = 1000
              const slices: {
                id: string
                text_preview: string
                qa_pairs: QnAPair[]
              }[] = []
              for (let i = 0; i < text.length; i += chunkSize) {
                const slice = text.slice(i, i + chunkSize)
                slices.push({
                  id: crypto.randomUUID(),
                  text_preview: slice,
                  qa_pairs: [],
                })
              }
              return slices
            })

            return {
              ...doc,
              parts: parts.length > 0 ? parts : doc.parts,
            }
          }),
        }))
        triggerSaveUiState()
      } catch (e) {
        console.error("Failed to load/slice extractions", e)
      }
    })()
  }

  type GenerationTarget =
    | { type: "all" }
    | { type: "document"; document_id: string }
    | { type: "part"; document_id: string; part_id: string }

  let pending_generation_target: GenerationTarget = { type: "all" }

  function handle_generate_for_document(
    e: CustomEvent<{ document_id: string }>,
  ) {
    pending_generation_target = {
      type: "document",
      document_id: e.detail.document_id,
    }
    open_generate_qna_modal()
  }

  function handle_generate_for_part(
    e: CustomEvent<{ document_id: string; part_id: string }>,
  ) {
    pending_generation_target = {
      type: "part",
      document_id: e.detail.document_id,
      part_id: e.detail.part_id,
    }
    open_generate_qna_modal()
  }

  function get_parts_for_target(target: GenerationTarget) {
    const indices: Array<{ docIdx: number; partIdx: number }> = []
    if (target.type === "all") {
      $saved_state.documents.forEach((doc, docIdx) => {
        doc.parts.forEach((_part, partIdx) => indices.push({ docIdx, partIdx }))
      })
    } else if (target.type === "document") {
      const docIdx = $saved_state.documents.findIndex(
        (d) => d.id === target.document_id,
      )
      if (docIdx !== -1) {
        $saved_state.documents[docIdx].parts.forEach((_p, partIdx) =>
          indices.push({ docIdx, partIdx }),
        )
      }
    } else if (target.type === "part") {
      const docIdx = $saved_state.documents.findIndex(
        (d) => d.id === target.document_id,
      )
      if (docIdx !== -1) {
        const partIdx = $saved_state.documents[docIdx].parts.findIndex(
          (p) => p.id === target.part_id,
        )
        if (partIdx !== -1) indices.push({ docIdx, partIdx })
      }
    }
    return indices
  }

  async function handle_generation_complete(event: CustomEvent) {
    const { pairs_per_part, guidance, model } = event.detail
    const model_provider = model.split("/")[0]
    const model_name = model.split("/").slice(1).join("/")

    // Build run config properties compatible with backend expectations
    const output_run_config_properties: RunConfigProperties = {
      model_name: model_name,
      // Type cast to satisfy enum type; server will validate
      model_provider_name: model_provider as unknown as ModelProviderName,
      prompt_id: "simple_prompt_builder",
      temperature: 1.0,
      top_p: 1.0,
      structured_output_mode: "default",
      tools_config: { tools: [] },
    }

    const targetParts = get_parts_for_target(pending_generation_target)
    generating_dialog?.show()

    try {
      for (const { docIdx, partIdx } of targetParts) {
        const partText =
          $saved_state.documents[docIdx].parts[partIdx].text_preview

        const { data, error } = await client.POST(
          "/api/projects/{project_id}/tasks/{task_id}/generate_qna",
          {
            body: {
              document_id: [],
              part_text: [partText],
              num_samples: pairs_per_part,
              output_run_config_properties,
              guidance: guidance || null,
              tags: null,
            },
            params: {
              path: {
                project_id,
                task_id,
              },
            },
          },
        )
        if (error) throw error

        const outputText = (data as unknown as { output: { output: string } })
          .output.output
        const response = JSON.parse(outputText) as {
          generated_qna_pairs?: Array<{ question: unknown; answer: unknown }>
        }
        const generated = Array.isArray(response.generated_qna_pairs)
          ? response.generated_qna_pairs
          : []

        const newPairs = generated.map((qa) => ({
          id: crypto.randomUUID(),
          question:
            typeof qa?.question === "string"
              ? qa.question
              : JSON.stringify(qa?.question ?? ""),
          answer:
            typeof qa?.answer === "string"
              ? qa.answer
              : JSON.stringify(qa?.answer ?? ""),
          generated: true,
          model_name,
          model_provider,
          saved_id: null,
        }))

        saved_state.update((s) => {
          const docs = [...s.documents]
          const doc = { ...docs[docIdx] }
          const parts = [...doc.parts]
          const part = { ...parts[partIdx] }
          part.qa_pairs = [...part.qa_pairs, ...newPairs]
          parts[partIdx] = part
          doc.parts = parts
          docs[docIdx] = doc
          return {
            ...s,
            generation_config: {
              pairs_per_part,
              part_size: s.generation_config.part_size,
              guidance,
            },
            documents: docs,
          }
        })
        triggerSaveUiState()
      }

      set_current_step(4)
    } catch (e) {
      console.error("Q&A generation failed", e)
    } finally {
      generating_dialog?.close()
    }
  }

  async function handle_extractor_config_selected(
    e: CustomEvent<{ extractor_config_id: string }>,
  ) {
    saved_state.update((s) => ({
      ...s,
      extractor_id: e.detail.extractor_config_id,
    }))
  }

  function delete_document(event: CustomEvent) {
    const { document_id } = event.detail
    saved_state.update((s) => ({
      ...s,
      documents: s.documents.filter((doc) => doc.id !== document_id),
    }))
    triggerSaveUiState()
  }

  function triggerSaveUiState() {
    // Just trigger reactivity - IndexedDB store handles persistence
    saved_state = saved_state
  }

  // Tag splits management
  function edit_splits() {
    editable_splits = Object.entries($saved_state.splits).map(
      ([tag, percent]) => ({
        tag,
        percent: percent * 100,
      }),
    )
    edit_splits_dialog?.show()
  }

  function add_split() {
    editable_splits = [...editable_splits, { tag: "", percent: 0 }]
  }

  function remove_split(index: number) {
    editable_splits = editable_splits.filter((_, i) => i !== index)
  }

  function get_total_percentage(
    splits: Array<{ tag: string; percent: number }>,
  ): number {
    return splits.reduce((sum, split) => sum + split.percent, 0)
  }

  function is_valid_splits(
    splits: Array<{ tag: string; percent: number }>,
  ): boolean {
    const total = get_total_percentage(splits)
    const has_empty_tags = splits.some((split) => split.tag.trim() === "")
    const has_negative_percent = splits.some((split) => split.percent < 0)

    return (
      (splits.length === 0 || Math.abs(total - 100) < 0.0001) &&
      !has_empty_tags &&
      !has_negative_percent
    )
  }

  function save_splits(): boolean {
    const new_splits: Record<string, number> = {}
    editable_splits.forEach((split) => {
      new_splits[split.tag] = split.percent / 100
    })
    saved_state.update((s) => ({ ...s, splits: new_splits }))
    edit_splits_dialog?.close()
    return true
  }

  function cancel_edit(): boolean {
    edit_splits_dialog?.close()
    return true
  }

  $: total_qa_pairs = $saved_state.documents.reduce(
    (total, doc) =>
      total +
      doc.parts.reduce(
        (partTotal: number, part: QnADocPart) =>
          partTotal + part.qa_pairs.length,
        0,
      ),
    0,
  )

  $: has_documents = $saved_state.documents.length > 0
  $: is_empty = !has_documents
</script>

<div class="max-w-[1400px]">
  <AppPage
    title="Search Tool Evaluator"
    no_y_padding
    sub_subtitle="Read the Docs"
    sub_subtitle_link="https://docs.kiln.tech/docs/qna-data-generation"
    action_buttons={[
      {
        label: "Reset",
        handler: () => {
          if (
            confirm(
              "Are you sure you want to clear all Q&A generation state? This cannot be undone.",
            )
          ) {
            clear_all_state()
            set_current_step(1)
          }
        },
      },
      {
        label: "Docs & Guide",
        href: "https://docs.kiln.tech/docs/qna-data-generation",
      },
    ]}
  >
    <!-- Header with Goal, Template, Tags -->
    <div class="card flex-row border px-6 py-3 mt-3 mb-2 shadow-sm text-sm">
      <div class="flex flex-row items-center gap-3 flex-grow">
        <div>
          <svg
            class="h-6 w-6 text-gray-500"
            viewBox="0 0 24 24"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
          >
            <path
              d="M5 22V14M5 14V4M5 14L7.47067 13.5059C9.1212 13.1758 10.8321 13.3328 12.3949 13.958C14.0885 14.6354 15.9524 14.7619 17.722 14.3195L17.9364 14.2659C18.5615 14.1096 19 13.548 19 12.9037V5.53669C19 4.75613 18.2665 4.18339 17.5092 4.3727C15.878 4.78051 14.1597 4.66389 12.5986 4.03943L12.3949 3.95797C10.8321 3.33284 9.1212 3.17576 7.47067 3.50587L5 4M5 4V2"
              stroke="currentColor"
              stroke-width="1.5"
              stroke-linecap="round"
            />
          </svg>
        </div>
        <div class="flex flex-col">
          <div class="text-xs text-gray-500 uppercase font-medium">Goal</div>
          <div class="whitespace-nowrap">
            Search Tool Evaluator
            <InfoTooltip
              tooltip_text="Generate question-answer pairs from document content"
              no_pad={true}
            />
          </div>
        </div>
      </div>
      <div
        class="border-l border-gray-200 self-stretch mx-4 border-[0.5px]"
      ></div>
      <div class="flex flex-row items-center gap-3 flex-grow">
        <div class="h-6 w-6 text-gray-500">
          <FileIcon kind="document" />
        </div>
        <div class="flex flex-col">
          <div class="text-xs text-gray-500 uppercase font-medium">
            Template
          </div>
          <div class="whitespace-nowrap">
            Q&A
            <InfoTooltip
              tooltip_text="Q&A generation template for extracting question-answer pairs from documents"
              no_pad={true}
            />
          </div>
        </div>
      </div>
      <div
        class="border-l border-gray-200 self-stretch mx-4 border-[0.5px]"
      ></div>
      <div class="flex flex-row items-center gap-3 flex-grow">
        <div>
          <svg
            class="h-6 w-6 text-gray-500"
            viewBox="0 0 24 24"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
          >
            <path
              d="M4.72848 16.1369C3.18295 14.5914 2.41018 13.8186 2.12264 12.816C1.83509 11.8134 2.08083 10.7485 2.57231 8.61875L2.85574 7.39057C3.26922 5.59881 3.47597 4.70292 4.08944 4.08944C4.70292 3.47597 5.59881 3.26922 7.39057 2.85574L8.61875 2.57231C10.7485 2.08083 11.8134 1.83509 12.816 2.12264C13.8186 2.41018 14.5914 3.18295 16.1369 4.72848L17.9665 6.55812C20.6555 9.24711 22 10.5916 22 12.2623C22 13.933 20.6555 15.2775 17.9665 17.9665C15.2775 20.6555 13.933 22 12.2623 22C10.5916 22 9.24711 20.6555 6.55812 17.9665L4.72848 16.1369Z"
              stroke="currentColor"
              stroke-width="1.5"
            />
            <circle
              cx="8.60724"
              cy="8.87891"
              r="2"
              transform="rotate(-45 8.60724 8.87891)"
              stroke="currentColor"
              stroke-width="1.5"
            />
          </svg>
        </div>
        <div class="flex flex-col">
          <div class="text-xs text-gray-500 uppercase font-medium">Tags</div>
          <div>
            <button class="hover:underline text-left" on:click={edit_splits}>
              {#if Object.keys($saved_state.splits).length == 0}
                No tag assignments
              {:else}
                {@const split_descriptions = Object.entries(
                  $saved_state.splits,
                ).map(([split, percent]) => `${split} (${percent * 100}%)`)}
                {split_descriptions.join(", ")}
              {/if}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Stepper -->
    <div
      class="pb-1 2xl:pt-1 mt-12 mb-4 gap-2 sticky top-0 z-2 backdrop-blur bg-white/70 z-10"
    >
      <div class="flex flex-col">
        <div class="flex justify-center">
          <ul class="steps">
            {#each step_numbers as step}
              <li class="step {current_step >= step ? 'step-primary' : ''}">
                <button
                  class="px-4 text-sm md:min-w-[155px] {current_step == step
                    ? 'font-medium cursor-default'
                    : 'text-gray-500 hover:underline hover:text-gray-700'}"
                  on:click={() => set_current_step(step)}
                  aria-label={`Go to step ${step} - ${step_names[step]}`}
                >
                  {step_names[step]}
                </button>
              </li>
            {/each}
          </ul>
        </div>
        <div class="max-w-3xl mx-auto mt-2 2xl:mt-4 text-center">
          <div class="font-light">
            <span class="font-medium">Step {current_step}:</span>
            {step_descriptions[current_step]}
          </div>
          <div class="mt-1 2xl:mt-2">
            {#if current_step == 1}
              <button
                class="btn btn-sm btn-primary"
                on:click={open_select_documents_modal}
              >
                Select Documents
              </button>
            {:else if current_step == 2}
              {#if !$saved_state.extraction_complete}
                <button
                  class="btn btn-sm btn-primary"
                  on:click={open_extraction_modal}
                  disabled={!has_documents}
                >
                  Run Extraction
                </button>
              {:else}
                <button
                  class="btn btn-sm btn-primary"
                  on:click={() => set_current_step(3)}
                >
                  Next Step
                </button>
              {/if}
            {:else if current_step == 3}
              <button
                class="btn btn-sm btn-primary"
                on:click={open_generate_qna_modal}
                disabled={!$saved_state.extraction_complete}
              >
                Generate Q&A Pairs
              </button>
            {:else if current_step == 4}
              <button class="btn btn-sm btn-primary">
                Save All ({total_qa_pairs} pairs)
              </button>
            {/if}
          </div>
        </div>
      </div>
    </div>

    <!-- Empty State or Table Display -->
    {#if is_empty}
      <QnaGenIntro on_select_documents={open_select_documents_modal} />
    {:else}
      <div class="rounded-lg border">
        <table class="table table-fixed">
          <thead class={total_qa_pairs === 0 ? "hidden-header" : ""}>
            <tr>
              <th style="width: calc(50% - 70px)"
                >Question <InfoTooltip
                  tooltip_text="The question to ask about the document content."
                  position="bottom"
                /></th
              >
              <th style="width: calc(50% - 110px)"
                >Answer <InfoTooltip
                  tooltip_text="The answer to the question based on the document content."
                  position="bottom"
                /></th
              >
              <th style="width: 140px">Status</th>
              <th style="width: 40px"></th>
            </tr>
          </thead>
          <tbody>
            {#each $saved_state.documents as document}
              <QnaDocumentNode
                {document}
                depth={1}
                triggerSave={triggerSaveUiState}
                on:delete_document={delete_document}
                on:generate_for_document={handle_generate_for_document}
                on:generate_for_part={handle_generate_for_part}
              />
            {/each}
          </tbody>
        </table>
      </div>
    {/if}
  </AppPage>
</div>

<!-- Modals -->
<SelectDocumentsModal
  bind:dialog={show_select_documents_modal}
  {project_id}
  {available_tags}
  on:documents_added={handle_documents_added}
  on:close={() => (current_dialog_type = null)}
  keyboard_submit={current_dialog_type === "select_documents"}
/>

<ExtractionModal
  keyboard_submit={current_dialog_type === "extraction"}
  bind:dialog={show_extraction_modal}
  bind:selected_extractor_id={$saved_state.extractor_id}
  bind:part_size={$saved_state.generation_config.part_size}
  on:extraction_complete={handle_extraction_complete}
  on:extractor_config_selected={handle_extractor_config_selected}
  on:close={() => (current_dialog_type = null)}
/>

<GenerateQnaModal
  bind:dialog={show_generate_qna_modal}
  {task_id}
  bind:pairs_per_part={$saved_state.generation_config.pairs_per_part}
  bind:guidance={$saved_state.generation_config.guidance}
  on:generation_complete={handle_generation_complete}
  on:close={() => (current_dialog_type = null)}
  keyboard_submit={current_dialog_type === "generate_qna"}
/>

<Dialog
  bind:this={generating_dialog}
  title="Generating Q&A"
  width="normal"
  action_buttons={[]}
>
  <div class="flex flex-row justify-center">
    <div class="loading loading-spinner loading-lg my-6"></div>
  </div>
</Dialog>

<Dialog
  title="Existing Session"
  bind:this={clear_existing_state_dialog}
  action_buttons={[
    {
      label: "New Session",
      action: clear_state_and_go_to_intro,
    },
    {
      label: "Continue Session",
      isPrimary: true,
      action: () => {
        clear_existing_state_dialog?.close()
        return true
      },
    },
  ]}
>
  <div class="flex flex-col gap-2">
    <div class="font-light flex flex-col gap-2">
      <p>A Q&A generation session is already in progress.</p>
    </div>
  </div></Dialog
>

<Dialog
  title="Edit Tag Assignments"
  bind:this={edit_splits_dialog}
  action_buttons={[
    {
      label: "Cancel",
      action: cancel_edit,
    },
    {
      label: "Save",
      action: save_splits,
      disabled: !is_valid_splits(editable_splits),
      isPrimary: true,
    },
  ]}
>
  <div class="font-light mb-4 text-sm">
    Tags will be randomly assigned to saved Q&A pairs in the following
    proportions:
  </div>

  {#if editable_splits.length === 0}
    <div class="font-medium my-16 text-center">
      No tags
      <div class="text-gray-500 font-normal text-sm">
        Data will be saved without tags
      </div>
      <button
        on:click={add_split}
        class="btn btn-sm btn-primary btn-outline mx-auto mt-4"
      >
        + Add Tag
      </button>
    </div>
  {:else}
    <div class="space-y-2 mt-12">
      {#each editable_splits as split, index}
        <div class="flex items-center gap-2">
          <input
            type="text"
            bind:value={split.tag}
            placeholder="Tag name"
            class="flex-1 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <input
            type="number"
            bind:value={split.percent}
            min="0"
            max="100"
            placeholder="0"
            class="w-20 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <span class="text-sm text-gray-500">%</span>
          <button
            on:click={() => remove_split(index)}
            class="px-2 py-1 hover:text-error hover:bg-red-50 rounded"
            title="Remove tag"
          >
            ×
          </button>
        </div>
      {/each}
    </div>

    <div class="flex flex-row items-center mt-3 mb-12">
      <div class="flex-1">
        <button on:click={add_split} class="btn btn-sm btn-primary btn-outline">
          + Add Tag
        </button>
      </div>
      <div class="text-gray-500 text-right">
        Total: {get_total_percentage(editable_splits).toFixed(1)}%
        {#if Math.abs(get_total_percentage(editable_splits) - 100) >= 0.000001}
          <div class="text-sm text-error ml-2">Must total 100%</div>
        {/if}
        {#if editable_splits.some((split) => split.tag === "")}
          <div class="text-sm text-error ml-2">
            Tags must be non-empty strings
          </div>
        {/if}
      </div>
    </div>
  {/if}
</Dialog>
