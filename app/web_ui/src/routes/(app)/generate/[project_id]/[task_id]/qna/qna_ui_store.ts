import {
  writable,
  derived,
  type Writable,
  type Readable,
  get,
} from "svelte/store"
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

type GenerationTarget =
  | { type: "all" }
  | { type: "document"; document_id: string }
  | { type: "part"; document_id: string; part_id: string }

type GenerationParams = {
  pairsPerPart: number
  guidance: string
  model: string
  chunkSizeTokens: number | null
  chunkOverlapTokens: number | null
}

export type QnaStore = {
  subscribe: (run: (s: QnASession) => void) => () => void
  status: Readable<"idle" | "running" | "done" | "error">
  progress: Readable<number>
  error: Readable<string | null>
  currentStep: Readable<StepNumber>
  maxStep: Readable<StepNumber>
  availableTags: Readable<string[]>
  pendingSaveCount: Readable<number>
  saveAllStatus: Readable<{
    running: boolean
    completed: boolean
    errors: Error[]
    savedCount: number
  }>

  extractorId: Writable<string | null>
  pairsPerPart: Writable<number>
  guidance: Writable<string>
  chunkSizeTokens: Writable<number | null>
  chunkOverlapTokens: Writable<number | null>

  init(defaultGuidance: string): Promise<void>
  destroy(): void
  setPendingTarget(target: GenerationTarget): void
  addDocuments(
    docs: Array<{ id: string; name: string; tags?: string[] }>,
    tags: string[],
  ): void
  setExtractor(id: string): void
  markExtractionComplete(id: string): void
  deleteDocument(id: string): void
  setSplits(splits: Record<string, number>): void
  removePair(documentId: string, partId: string, qaId: string): void
  removePart(documentId: string, partId: string): void
  setCurrentStep(step: StepNumber): void
  clearAll(defaultGuidance: string): void
  fetchAvailableTags(): Promise<void>
  generate(params: GenerationParams): Promise<void>
  saveAll(sessionId: string): Promise<void>
}

export function createQnaStore(projectId: string, taskId: string): QnaStore {
  const _state = writable<QnASession>({
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

  const status = writable<"idle" | "running" | "done" | "error">("idle")
  const progress = writable<number>(0)
  const error = writable<string | null>(null)
  const availableTags = writable<string[]>([])
  const pendingTarget = writable<GenerationTarget>({ type: "all" })
  const manualStep = writable<StepNumber | null>(null)
  const _maxStep = writable<StepNumber>(1)

  const _saveAllRunning = writable<boolean>(false)
  const _saveAllCompleted = writable<boolean>(false)
  const _saveAllErrors = writable<Error[]>([])
  const _savedCount = writable<number>(0)
  const extractorId = writable<string | null>(null)
  const pairsPerPart = writable<number>(5)
  const guidance = writable<string>("")
  const chunkSizeTokens = writable<number | null>(null)
  const chunkOverlapTokens = writable<number | null>(null)

  let persistenceUnsubscribe: (() => void) | null = null

  async function init(defaultGuidance: string): Promise<void> {
    const key = `qna_data_${projectId}_${taskId}`
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

    const initialValue = get(store)
    if (initialValue) {
      _state.set(initialValue)
      // Sync simple writables from loaded state
      extractorId.set(initialValue.extractor_id)
      pairsPerPart.set(initialValue.generation_config.pairs_per_part)
      guidance.set(initialValue.generation_config.guidance)
      chunkSizeTokens.set(initialValue.generation_config.chunk_size_tokens)
      chunkOverlapTokens.set(
        initialValue.generation_config.chunk_overlap_tokens,
      )
    }

    // Persist state to IndexedDB
    persistenceUnsubscribe = _state.subscribe((value) => {
      ;(store as Writable<QnASession>).set(value)
    })

    // Sync simple writables to state when they change
    extractorId.subscribe((value) => {
      _state.update((s) => ({ ...s, extractor_id: value }))
    })
    pairsPerPart.subscribe((value) => {
      _state.update((s) => ({
        ...s,
        generation_config: { ...s.generation_config, pairs_per_part: value },
      }))
    })
    guidance.subscribe((value) => {
      _state.update((s) => ({
        ...s,
        generation_config: { ...s.generation_config, guidance: value },
      }))
    })
    chunkSizeTokens.subscribe((value) => {
      _state.update((s) => ({
        ...s,
        generation_config: {
          ...s.generation_config,
          chunk_size_tokens: value,
        },
      }))
    })
    chunkOverlapTokens.subscribe((value) => {
      _state.update((s) => ({
        ...s,
        generation_config: {
          ...s.generation_config,
          chunk_overlap_tokens: value,
        },
      }))
    })
  }

  function destroy(): void {
    if (persistenceUnsubscribe) {
      persistenceUnsubscribe()
      persistenceUnsubscribe = null
    }
  }

  const autoStep = derived(_state, ($state): StepNumber => {
    const hasQaPairs = $state.documents.some((d) =>
      d.parts.some((p) => p.qa_pairs.length > 0),
    )
    if (hasQaPairs) return 4
    if ($state.extraction_complete) return 3
    if ($state.documents.length > 0) return 2
    return 1
  })

  const currentStep = derived(
    [manualStep, autoStep],
    ([$manual, $auto]): StepNumber => $manual ?? $auto,
  )

  const maxStep = derived(
    [_maxStep, autoStep],
    ([$max, $auto]): StepNumber => Math.max($max, $auto) as StepNumber,
  )

  const pendingSaveCount = derived(_state, ($state): number => {
    let count = 0
    $state.documents.forEach((doc) => {
      doc.parts.forEach((part) => {
        part.qa_pairs.forEach((pair) => {
          if (!pair.saved_id) count++
        })
      })
    })
    return count
  })

  const saveAllStatus = derived(
    [_saveAllRunning, _saveAllCompleted, _saveAllErrors, _savedCount],
    ([$running, $completed, $errors, $saved]) => ({
      running: $running,
      completed: $completed,
      errors: $errors,
      savedCount: $saved,
    }),
  )

  function setPendingTarget(target: GenerationTarget): void {
    pendingTarget.set(target)
  }

  function addDocuments(
    documents: Array<{ id: string; name: string; tags?: string[] }>,
    tags: string[],
  ): void {
    extractorId.set(null)
    _state.update((s) => {
      const newDocuments: QnADocumentNode[] = documents.map((doc) => ({
        id: doc.id,
        name: doc.name,
        tags: doc.tags || [],
        extracted: false,
        parts: [],
      }))
      return {
        ...s,
        documents: [...s.documents, ...newDocuments],
        selected_tags: tags,
        extraction_complete: false,
      }
    })
    manualStep.set(null)
  }

  function setExtractor(extractorConfigId: string): void {
    extractorId.set(extractorConfigId)
  }

  function markExtractionComplete(extractorConfigId: string): void {
    extractorId.set(extractorConfigId)
    _state.update((s) => ({
      ...s,
      extraction_complete: true,
      documents: s.documents.map((doc) => ({ ...doc, extracted: true })),
    }))
  }

  function deleteDocument(documentId: string): void {
    _state.update((s) => {
      const newDocuments = s.documents.filter((doc) => doc.id !== documentId)
      if (newDocuments.length === 0) {
        extractorId.set(null)
        return {
          ...s,
          documents: newDocuments,
          extraction_complete: false,
        }
      }
      return {
        ...s,
        documents: newDocuments,
      }
    })
    if (get(_state).documents.length === 0) {
      manualStep.set(null)
    }
  }

  function setSplits(splits: Record<string, number>): void {
    _state.update((s) => ({ ...s, splits }))
  }

  function removePair(documentId: string, partId: string, qaId: string): void {
    _state.update((s) => {
      const docs = s.documents.map((doc) => {
        if (doc.id !== documentId) return doc
        const parts = doc.parts.map((p) =>
          p.id === partId
            ? { ...p, qa_pairs: p.qa_pairs.filter((qa) => qa.id !== qaId) }
            : p,
        )
        return { ...doc, parts }
      })
      return { ...s, documents: docs }
    })
  }

  function removePart(documentId: string, partId: string): void {
    _state.update((s) => {
      const docs = s.documents.map((doc) =>
        doc.id === documentId
          ? { ...doc, parts: doc.parts.filter((p) => p.id !== partId) }
          : doc,
      )
      return { ...s, documents: docs }
    })
  }

  function setCurrentStep(step: StepNumber): void {
    const currentAutoStep = get(autoStep)
    if (step <= currentAutoStep) {
      manualStep.set(step)
    }
    _maxStep.update((max) => Math.max(max, step) as StepNumber)
  }

  function clearAll(defaultGuidance: string): void {
    manualStep.set(1)
    _maxStep.set(1)
    _state.update((s) => ({
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

  async function fetchAvailableTags(): Promise<void> {
    try {
      const { data, error: apiError } = await client.GET(
        "/api/projects/{project_id}/documents/tags",
        { params: { path: { project_id: projectId } } },
      )
      if (apiError) throw apiError
      availableTags.set(data || [])
    } catch (e) {
      console.error("Error loading tags:", e)
      availableTags.set([])
    }
  }

  function getPartsForTarget(
    state: QnASession,
    target: GenerationTarget,
  ): Array<{ docIdx: number; partIdx: number }> {
    const indices: Array<{ docIdx: number; partIdx: number }> = []
    if (target.type === "all") {
      state.documents.forEach((_, docIdx) => {
        state.documents[docIdx].parts.forEach((_, partIdx) =>
          indices.push({ docIdx, partIdx }),
        )
      })
    } else if (target.type === "document") {
      const docIdx = state.documents.findIndex(
        (d) => d.id === target.document_id,
      )
      if (docIdx !== -1) {
        state.documents[docIdx].parts.forEach((_, partIdx) =>
          indices.push({ docIdx, partIdx }),
        )
      }
    } else if (target.type === "part") {
      const docIdx = state.documents.findIndex(
        (d) => d.id === target.document_id,
      )
      if (docIdx !== -1) {
        const partIdx = state.documents[docIdx].parts.findIndex(
          (p) => p.id === target.part_id,
        )
        if (partIdx !== -1) indices.push({ docIdx, partIdx })
      }
    }
    return indices
  }

  async function fetchChunksForDoc(
    docIdx: number,
    extractorId: string,
    chunkSizeTokens: number | null,
    chunkOverlapTokens: number | null,
  ): Promise<void> {
    const state = get(_state)
    const doc = state.documents[docIdx]
    const body = {
      chunk_size: chunkSizeTokens ?? null,
      chunk_overlap: chunkOverlapTokens ?? null,
    }
    const res = await fetch(
      `${base_url}/api/projects/${projectId}/extractor_configs/${extractorId}/documents/${doc.id}/ephemeral_split`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      },
    )
    if (!res.ok) throw new Error(`Chunking failed for ${doc.id}`)
    const data: { chunks: Array<{ id: string; text: string }> } =
      await res.json()
    const parts: QnADocPart[] = data.chunks.map((c) => ({
      id: c.id,
      text_preview: c.text,
      qa_pairs: [] as QnAPair[],
    }))
    _state.update((s) => {
      const docs = [...s.documents]
      const d = { ...docs[docIdx] }
      d.parts = parts
      docs[docIdx] = d
      return { ...s, documents: docs }
    })
  }

  async function runChunkingQueue(
    queue: number[],
    extractorId: string,
    chunkSizeTokens: number | null,
    chunkOverlapTokens: number | null,
    concurrency: number = 5,
  ): Promise<void> {
    async function worker() {
      while (queue.length > 0) {
        const idx = queue.shift()!
        await fetchChunksForDoc(
          idx,
          extractorId,
          chunkSizeTokens,
          chunkOverlapTokens,
        )
      }
    }
    const workers = Array(concurrency)
      .fill(null)
      .map(() => worker())
    await Promise.all(workers)
  }

  async function generate(params: GenerationParams): Promise<void> {
    const {
      pairsPerPart,
      guidance,
      model,
      chunkSizeTokens,
      chunkOverlapTokens,
    } = params

    const modelProvider = model.split("/")[0]
    const modelName = model.split("/").slice(1).join("/")

    const outputRunConfigProperties: RunConfigProperties = {
      model_name: modelName,
      model_provider_name: modelProvider as unknown as ModelProviderName,
      prompt_id: "simple_prompt_builder",
      temperature: 1.0,
      top_p: 1.0,
      structured_output_mode: "default",
      tools_config: { tools: [] },
    }

    status.set("running")
    progress.set(0)
    error.set(null)

    try {
      const state = get(_state)
      const targetSel = get(pendingTarget)
      const targetDocs = new Set<number>()

      if (targetSel.type === "all") {
        state.documents.forEach((_, docIdx) => {
          targetDocs.add(docIdx)
        })
      } else if (targetSel.type === "document") {
        const docIdx = state.documents.findIndex(
          (d) => d.id === targetSel.document_id,
        )
        if (docIdx !== -1) targetDocs.add(docIdx)
      } else if (targetSel.type === "part") {
        const docIdx = state.documents.findIndex(
          (d) => d.id === targetSel.document_id,
        )
        if (docIdx !== -1) targetDocs.add(docIdx)
      }

      const queue: Array<number> = []
      if (targetSel.type === "all") {
        targetDocs.forEach((docIdx) => {
          const s = get(_state)
          const doc = s.documents[docIdx]
          const hasParts = doc.parts && doc.parts.length > 0
          const shouldReplace = hasParts && chunkSizeTokens !== null
          if (!hasParts || shouldReplace) {
            queue.push(docIdx)
          }
        })

        const extractorId = get(_state).extractor_id
        if (extractorId) {
          await runChunkingQueue(
            queue,
            extractorId,
            chunkSizeTokens ?? null,
            chunkOverlapTokens ?? null,
            5,
          )
        }
      }

      const freshTargetParts = getPartsForTarget(get(_state), targetSel)
      let completed = 0
      for (const { docIdx, partIdx } of freshTargetParts) {
        const partText =
          get(_state).documents[docIdx].parts[partIdx].text_preview

        const { data, error: apiError } = await client.POST(
          "/api/projects/{project_id}/tasks/{task_id}/generate_qna",
          {
            body: {
              document_id: [],
              part_text: [partText],
              num_samples: pairsPerPart,
              output_run_config_properties: outputRunConfigProperties,
              guidance: guidance || null,
              tags: null,
            },
            params: { path: { project_id: projectId, task_id: taskId } },
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
          model_name: modelName,
          model_provider: modelProvider,
          saved_id: null,
        }))

        _state.update((s) => {
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
              pairs_per_part: pairsPerPart,
              guidance,
              chunk_size_tokens: chunkSizeTokens,
              chunk_overlap_tokens: chunkOverlapTokens,
            },
            documents: docs,
          }
        })
        completed += 1
        progress.set(Math.round((completed / freshTargetParts.length) * 100))
      }

      setCurrentStep(4)
      status.set("done")
    } catch (e: unknown) {
      console.error("Q&A generation failed", e)
      const message =
        typeof e === "object" && e !== null && "message" in e
          ? String((e as { message: unknown }).message)
          : String(e)
      error.set(message)
      status.set("error")
    }
  }

  async function saveAll(sessionId: string): Promise<void> {
    try {
      _saveAllRunning.set(true)
      _saveAllCompleted.set(false)
      _saveAllErrors.set([])
      _savedCount.set(0)

      const queue: Array<{
        docIdx: number
        partIdx: number
        pairIdx: number
      }> = []
      const s = get(_state)
      s.documents.forEach((doc, docIdx) => {
        doc.parts.forEach((part, partIdx) => {
          part.qa_pairs.forEach((pair, pairIdx) => {
            if (!pair.saved_id) queue.push({ docIdx, partIdx, pairIdx })
          })
        })
      })

      for (const { docIdx, partIdx, pairIdx } of queue) {
        const ss = get(_state)
        const pair = ss.documents[docIdx].parts[partIdx].qa_pairs[pairIdx]
        const splits = ss.splits
        const keys = Object.keys(splits)
        const splitTag =
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
                path: { project_id: projectId, task_id: taskId },
                query: { session_id: sessionId },
              },
              body: {
                question: pair.question,
                answer: pair.answer,
                model_name: pair.model_name,
                model_provider: pair.model_provider,
                tags: splitTag ? [splitTag] : null,
              },
            },
          )
          if (
            apiError ||
            !data ||
            typeof (data as unknown as { id?: unknown }).id !== "string"
          )
            throw apiError || new Error("Save failed")

          const savedId = (data as unknown as { id: string }).id
          _state.update((s) => {
            const docs = [...s.documents]
            const doc = { ...docs[docIdx] }
            const parts = [...doc.parts]
            const part = { ...parts[partIdx] }
            const pairs = [...part.qa_pairs]
            const updated = { ...pairs[pairIdx], saved_id: savedId }
            pairs[pairIdx] = updated
            part.qa_pairs = pairs
            parts[partIdx] = part
            doc.parts = parts
            docs[docIdx] = doc
            return { ...s, documents: docs }
          })
          _savedCount.update((c) => c + 1)
        } catch (e) {
          _saveAllErrors.update((arr) => [...arr, e as Error])
        }
      }
    } finally {
      _saveAllRunning.set(false)
      _saveAllCompleted.set(true)
    }
  }

  return {
    subscribe: _state.subscribe,
    status,
    progress,
    error,
    currentStep,
    maxStep,
    availableTags,
    pendingSaveCount,
    saveAllStatus,
    extractorId,
    pairsPerPart,
    guidance,
    chunkSizeTokens,
    chunkOverlapTokens,
    init,
    destroy,
    setPendingTarget,
    addDocuments,
    setExtractor,
    markExtractionComplete,
    deleteDocument,
    setSplits,
    removePair,
    removePart,
    setCurrentStep,
    clearAll,
    fetchAvailableTags,
    generate,
    saveAll,
  }
}
