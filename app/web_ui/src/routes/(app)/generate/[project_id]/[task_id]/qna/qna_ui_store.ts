import { get, writable, derived, type Writable } from "svelte/store"
import { client, base_url } from "$lib/api_client"
import { indexedDBStore } from "$lib/stores/index_db_store"
import type { ModelProviderName, RunConfigProperties } from "$lib/types"

export type StepNumber = 1 | 2 | 3 | 4
export const step_numbers: StepNumber[] = [1, 2, 3, 4]
export const step_names: Record<StepNumber, string> = {
  1: "Select Documents",
  2: "Extraction",
  3: "Generate Q&A",
  4: "Save Data",
}

export const step_descriptions: Record<StepNumber, string> = {
  1: "Choose which documents to generate Q&A pairs from",
  2: "Extract text content from selected documents",
  3: "Generate question and answer pairs from extracted content",
  4: "Save generated Q&A pairs to dataset",
}

export const current_step = writable<StepNumber>(1)
export const max_available_step = writable<StepNumber>(1)

export function set_current_step(step: StepNumber) {
  current_step.set(step)

  max_available_step.set(Math.max(get(max_available_step), step) as StepNumber)
}

export function reset_ui_store() {
  current_step.set(1)
  max_available_step.set(1)
}

// --- QnA generation orchestrator (Option A: thin store with methods) ---

type Status = "idle" | "running" | "done" | "error"

export const generationStatus = writable<Status>("idle")
export const progress = writable<number>(0)
export const error = writable<string | null>(null)
export const isGenerating = derived(generationStatus, ($s) => $s === "running")

export type QnAPair = {
  id: string
  question: string
  answer: string
  generated: boolean
  model_name?: string
  model_provider?: string
  saved_id: string | null
}

export type QnADocPart = {
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

export type QnASession = {
  selected_tags: string[]
  extractor_id: string | null
  extraction_complete: boolean
  generation_config: {
    pairs_per_part: number
    guidance: string
    chunk_size_tokens: number | null
    chunk_overlap_tokens: number | null
  }
  documents: QnADocumentNode[]
  splits: Record<string, number>
}

export const saved_state: Writable<QnASession> = writable<QnASession>({
  selected_tags: [],
  extractor_id: null,
  extraction_complete: false,
  generation_config: {
    pairs_per_part: 5,
    guidance: "",
    chunk_size_tokens: null,
    chunk_overlap_tokens: null,
  },
  documents: [],
  splits: {},
})

export async function initSession(
  project_id: string,
  task_id: string,
  defaultGuidance: string,
): Promise<Writable<QnASession>> {
  const key = `qna_data_${project_id}_${task_id}`
  const { store, initialized } = indexedDBStore<QnASession>(key, {
    selected_tags: [],
    extractor_id: null,
    extraction_complete: false,
    generation_config: {
      pairs_per_part: 5,
      guidance: defaultGuidance,
      chunk_size_tokens: null,
      chunk_overlap_tokens: null,
    },
    documents: [],
    splits: {},
  })
  await initialized

  // Hydrate the existing saved_state without reassigning the store reference
  const initialValue = get(store)
  if (initialValue) {
    saved_state.set(initialValue)
  }

  // Bridge updates from the UI store to the IndexedDB-backed store for persistence
  // Note: we avoid subscribing store -> saved_state to prevent circular updates;
  // the UI exclusively writes to saved_state.
  saved_state.subscribe((value) => {
    // Forward to persistence layer (no-op if unchanged)
    ;(store as Writable<QnASession>).set(value)
  })

  return saved_state
}

export const availableTags = writable<string[]>([])
export async function fetchAvailableTags(project_id: string) {
  try {
    const { data, error: apiError } = await client.GET(
      "/api/projects/{project_id}/documents/tags",
      { params: { path: { project_id } } },
    )
    if (apiError) throw apiError
    availableTags.set(data || [])
  } catch (e) {
    console.error("Error loading tags:", e)
    availableTags.set([])
  }
}

// ---- Step computation based on current state ----
export function recomputeStep() {
  const stateNow = get(saved_state)
  const hasQaPairs = stateNow.documents.some((d) =>
    d.parts.some((p) => p.qa_pairs.length > 0),
  )
  if (hasQaPairs) {
    set_current_step(4)
  } else if (stateNow.extraction_complete) {
    set_current_step(3)
  } else if (stateNow.documents.length > 0) {
    set_current_step(2)
  } else {
    set_current_step(1)
  }
}

// ---- Save All state and action ----
export const saveAllRunning = writable<boolean>(false)
export const saveAllCompleted = writable<boolean>(false)
export const saveAllSubErrors = writable<Error[]>([])
export const savedCount = writable<number>(0)

function getPairsToSaveIndices(): Array<{
  docIdx: number
  partIdx: number
  pairIdx: number
}> {
  const indices: Array<{ docIdx: number; partIdx: number; pairIdx: number }> =
    []
  const s = get(saved_state)
  s.documents.forEach((doc, docIdx) => {
    doc.parts.forEach((part, partIdx) => {
      part.qa_pairs.forEach((pair, pairIdx) => {
        if (!pair.saved_id) indices.push({ docIdx, partIdx, pairIdx })
      })
    })
  })
  return indices
}

export async function saveAllQnaPairs(
  project_id: string,
  task_id: string,
  session_id: string,
) {
  try {
    saveAllRunning.set(true)
    saveAllCompleted.set(false)
    saveAllSubErrors.set([])
    savedCount.set(0)

    const queue = getPairsToSaveIndices()
    for (const { docIdx, partIdx, pairIdx } of queue) {
      const ss = get(saved_state)
      const pair = ss.documents[docIdx].parts[partIdx].qa_pairs[pairIdx]
      const splits = ss.splits
      const keys = Object.keys(splits)
      const split_tag =
        keys.length > 0
          ? (() => {
              const r = Math.random()
              let acc = 0
              for (const k of keys) {
                acc += splits[k]
                if (r <= acc) return k
              }
              return keys[0]
            })()
          : undefined

      if (!pair.model_name || !pair.model_provider) {
        throw new Error("Model name and provider are required")
      }

      try {
        const { data, error: apiError } = await client.POST(
          "/api/projects/{project_id}/tasks/{task_id}/save_qna_pair",
          {
            params: {
              path: { project_id, task_id },
              query: { session_id },
            },
            body: {
              question: pair.question,
              answer: pair.answer,
              model_name: pair.model_name,
              model_provider: pair.model_provider,
              tags: split_tag ? [split_tag] : null,
            },
          },
        )
        if (
          apiError ||
          !data ||
          typeof (data as unknown as { id?: unknown }).id !== "string"
        )
          throw apiError || new Error("Save failed")

        const saved_id = (data as unknown as { id: string }).id
        saved_state.update((s: QnASession) => {
          const docs = [...s.documents]
          const doc = { ...docs[docIdx] }
          const parts = [...doc.parts]
          const part = { ...parts[partIdx] }
          const pairs = [...part.qa_pairs]
          const updated = { ...pairs[pairIdx], saved_id }
          pairs[pairIdx] = updated
          part.qa_pairs = pairs
          parts[partIdx] = part
          doc.parts = parts
          docs[docIdx] = doc
          return { ...s, documents: docs }
        })
        savedCount.update((c) => c + 1)
        triggerSaveUiState()
      } catch (e) {
        saveAllSubErrors.update((arr) => [...arr, e as Error])
      }
    }
  } finally {
    saveAllRunning.set(false)
    saveAllCompleted.set(true)
  }
}

export function getPairsToSave(): Array<{
  docIdx: number
  partIdx: number
  pairIdx: number
}> {
  return getPairsToSaveIndices()
}

export function pendingSaveCount(): number {
  return getPairsToSaveIndices().length
}

export function clearAllState(defaultGuidance: string) {
  reset_ui_store()
  saved_state.update((s) => ({
    ...s,
    selected_tags: [],
    extractor_id: null,
    extraction_complete: false,
    generation_config: {
      pairs_per_part: 5,
      guidance: defaultGuidance,
      chunk_size_tokens: null,
      chunk_overlap_tokens: null,
    },
    documents: [],
    splits: {},
  }))
}

export function triggerSaveUiState() {
  // Touch store to notify subscribers; underlying indexedDB store persists
  saved_state.update((s) => s)
}

// Generation target selection
export const pending_generation_target = writable<GenerationTarget>({
  type: "all",
})
export function setPendingGenerationTarget(target: GenerationTarget) {
  pending_generation_target.set(target)
}

// --- Centralized state actions ---
export function addDocuments(
  documents: Array<{ id: string; name: string; tags?: string[] }>,
  tags: string[],
) {
  const new_documents: QnADocumentNode[] = documents.map((doc) => ({
    id: doc.id,
    name: doc.name,
    tags: doc.tags || [],
    extracted: false,
    parts: [],
  }))
  saved_state.update((s) => ({
    ...s,
    documents: [...s.documents, ...new_documents],
    selected_tags: tags,
  }))
  triggerSaveUiState()
}

export function setExtractorId(extractor_config_id: string) {
  saved_state.update((s) => ({ ...s, extractor_id: extractor_config_id }))
}

export function markExtractionComplete(extractor_config_id: string) {
  saved_state.update((s) => ({
    ...s,
    extractor_id: extractor_config_id,
    extraction_complete: true,
    documents: s.documents.map((doc) => ({ ...doc, extracted: true })),
  }))
  triggerSaveUiState()
}

export function deleteDocument(document_id: string) {
  saved_state.update((s) => ({
    ...s,
    documents: s.documents.filter((doc) => doc.id !== document_id),
  }))
  triggerSaveUiState()
}

export function setSplits(splits: Record<string, number>) {
  saved_state.update((s) => ({ ...s, splits }))
}

export function removeQAPair(
  document_id: string,
  part_id: string,
  qa_id: string,
) {
  saved_state.update((s) => {
    const docs = s.documents.map((doc) => {
      if (doc.id !== document_id) return doc
      const parts = doc.parts.map((p) =>
        p.id === part_id
          ? { ...p, qa_pairs: p.qa_pairs.filter((qa) => qa.id !== qa_id) }
          : p,
      )
      return { ...doc, parts }
    })
    return { ...s, documents: docs }
  })
  triggerSaveUiState()
}

export function removePart(document_id: string, part_id: string) {
  saved_state.update((s) => {
    const docs = s.documents.map((doc) =>
      doc.id === document_id
        ? { ...doc, parts: doc.parts.filter((p) => p.id !== part_id) }
        : doc,
    )
    return { ...s, documents: docs }
  })
  triggerSaveUiState()
}
type GenerationTarget =
  | { type: "all" }
  | { type: "document"; document_id: string }
  | { type: "part"; document_id: string; part_id: string }

type HandleGenerationParams = {
  pairs_per_part: number
  guidance: string
  model: string
  chunk_size_tokens: number | null
  chunk_overlap_tokens: number | null
}

type HandleGenerationContext = {
  project_id: string
  task_id: string
  // writable-like store from indexedDBStore
  saved_state: Writable<QnASession>
  get_state: () => QnASession // getter for current saved_state value
  triggerSaveUiState: () => void
  pending_generation_target: GenerationTarget
  set_current_step: (s: StepNumber) => void
}

function get_parts_for_target(
  saved_state: QnASession,
  target: GenerationTarget,
) {
  const indices: Array<{ docIdx: number; partIdx: number }> = []
  if (target.type === "all") {
    saved_state.documents.forEach((_doc: QnADocumentNode, docIdx: number) => {
      saved_state.documents[docIdx].parts.forEach(
        (_part: QnADocPart, partIdx: number) =>
          indices.push({ docIdx, partIdx }),
      )
    })
  } else if (target.type === "document") {
    const docIdx = saved_state.documents.findIndex(
      (d: QnADocumentNode) => d.id === target.document_id,
    )
    if (docIdx !== -1) {
      saved_state.documents[docIdx].parts.forEach(
        (_p: QnADocPart, partIdx: number) => indices.push({ docIdx, partIdx }),
      )
    }
  } else if (target.type === "part") {
    const docIdx = saved_state.documents.findIndex(
      (d: QnADocumentNode) => d.id === target.document_id,
    )
    if (docIdx !== -1) {
      const partIdx = saved_state.documents[docIdx].parts.findIndex(
        (p: QnADocPart) => p.id === target.part_id,
      )
      if (partIdx !== -1) indices.push({ docIdx, partIdx })
    }
  }
  return indices
}

async function fetch_chunks_for_doc(
  saved_state: QnASession,
  update_saved_state: HandleGenerationContext["saved_state"]["update"],
  project_id: string,
  docIdx: number,
  extractor_id: string,
  chunk_size_tokens: number | null,
  chunk_overlap_tokens: number | null,
) {
  const doc = saved_state.documents[docIdx]
  const body: { chunk_size: number | null; chunk_overlap: number | null } = {
    chunk_size: chunk_size_tokens ?? null,
    chunk_overlap: chunk_overlap_tokens ?? null,
  }
  const res = await fetch(
    `${base_url}/api/projects/${project_id}/extractor_configs/${extractor_id}/documents/${doc.id}/ephemeral_split`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  )
  if (!res.ok) throw new Error(`Chunking failed for ${doc.id}`)
  const data: { chunks: Array<{ id: string; text: string }> } = await res.json()
  const parts: QnADocPart[] = data.chunks.map((c) => ({
    id: c.id,
    text_preview: c.text,
    qa_pairs: [] as QnAPair[],
  }))
  update_saved_state((s: QnASession) => {
    const docs: QnADocumentNode[] = [...s.documents]
    const d: QnADocumentNode = { ...docs[docIdx] }
    d.parts = parts
    docs[docIdx] = d
    return { ...s, documents: docs }
  })
}

async function run_chunking_queue(
  saved_state: QnASession,
  update_saved_state: HandleGenerationContext["saved_state"]["update"],
  project_id: string,
  queue: number[],
  extractor_id: string,
  chunk_size_tokens: number | null,
  chunk_overlap_tokens: number | null,
  concurrency: number = 5,
) {
  async function worker() {
    while (queue.length > 0) {
      const idx = queue.shift()!
      await fetch_chunks_for_doc(
        saved_state,
        update_saved_state,
        project_id,
        idx,
        extractor_id,
        chunk_size_tokens,
        chunk_overlap_tokens,
      )
    }
  }
  const workers = Array(concurrency)
    .fill(null)
    .map(() => worker())
  await Promise.all(workers)
}

export async function handleGenerationComplete(
  params: HandleGenerationParams,
  ids: { project_id: string; task_id: string },
) {
  const {
    pairs_per_part,
    guidance,
    model,
    chunk_size_tokens,
    chunk_overlap_tokens,
  } = params
  const { project_id, task_id } = ids

  const model_provider = model.split("/")[0]
  const model_name = model.split("/").slice(1).join("/")

  const output_run_config_properties: RunConfigProperties = {
    model_name: model_name,
    model_provider_name: model_provider as unknown as ModelProviderName,
    prompt_id: "simple_prompt_builder",
    temperature: 1.0,
    top_p: 1.0,
    structured_output_mode: "default",
    tools_config: { tools: [] },
  }

  generationStatus.set("running")
  progress.set(0)
  error.set(null)

  try {
    // Determine target documents
    const state_now: QnASession = get(saved_state)
    const targetSel = get(pending_generation_target)
    const targetDocs = new Set<number>()
    if (targetSel.type === "all") {
      state_now.documents.forEach((_doc: QnADocumentNode, docIdx: number) => {
        targetDocs.add(docIdx)
      })
    } else if (targetSel.type === "document") {
      const t = targetSel
      const docIdx = state_now.documents.findIndex(
        (d: QnADocumentNode) => d.id === t.document_id,
      )
      if (docIdx !== -1) targetDocs.add(docIdx)
    } else if (targetSel.type === "part") {
      const t = targetSel
      const docIdx = state_now.documents.findIndex(
        (d: QnADocumentNode) => d.id === t.document_id,
      )
      if (docIdx !== -1) targetDocs.add(docIdx)
    }

    // Queue chunking if needed
    const queue: Array<number> = []
    targetDocs.forEach((docIdx) => {
      const ss: QnASession = get(saved_state)
      const doc = ss.documents[docIdx]
      const hasParts = doc.parts && doc.parts.length > 0
      const shouldReplace = hasParts && chunk_size_tokens !== null
      if (!hasParts || shouldReplace) {
        queue.push(docIdx)
      }
    })

    const extractor_id: string | null = get(saved_state).extractor_id
    if (extractor_id) {
      await run_chunking_queue(
        get(saved_state),
        (updater) => saved_state.update(updater),
        project_id,
        queue,
        extractor_id,
        chunk_size_tokens ?? null,
        chunk_overlap_tokens ?? null,
        5,
      )
      triggerSaveUiState()
    }

    // Generate for fresh target parts
    const freshTargetParts = get_parts_for_target(get(saved_state), targetSel)
    let completed = 0
    for (const { docIdx, partIdx } of freshTargetParts) {
      const partText =
        get(saved_state).documents[docIdx].parts[partIdx].text_preview

      const { data, error: apiError } = await client.POST(
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
          params: { path: { project_id, task_id } },
        },
      )
      if (apiError) throw apiError

      const outputText = (data as unknown as { output: { output: string } })
        .output.output
      const response = JSON.parse(outputText) as {
        generated_qna_pairs?: Array<{ question: unknown; answer: unknown }>
      }
      const generated = Array.isArray(response.generated_qna_pairs)
        ? response.generated_qna_pairs
        : []

      const newPairs: QnAPair[] = generated.map((qa) => ({
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

      saved_state.update((s: QnASession) => {
        const docs: QnADocumentNode[] = [...s.documents]
        const doc: QnADocumentNode = { ...docs[docIdx] }
        const parts: QnADocPart[] = [...doc.parts]
        const part: QnADocPart = { ...parts[partIdx] }
        part.qa_pairs = [...part.qa_pairs, ...newPairs]
        parts[partIdx] = part
        doc.parts = parts
        docs[docIdx] = doc
        return {
          ...s,
          generation_config: {
            pairs_per_part,
            guidance,
            chunk_size_tokens,
            chunk_overlap_tokens,
          },
          documents: docs,
        }
      })
      triggerSaveUiState()
      completed += 1
      progress.set(Math.round((completed / freshTargetParts.length) * 100))
    }

    set_current_step(4)
    generationStatus.set("done")
  } catch (e: unknown) {
    console.error("Q&A generation failed", e)
    const message =
      typeof e === "object" && e !== null && "message" in e
        ? String((e as { message: unknown }).message)
        : String(e)
    error.set(message)
    generationStatus.set("error")
  }
}
