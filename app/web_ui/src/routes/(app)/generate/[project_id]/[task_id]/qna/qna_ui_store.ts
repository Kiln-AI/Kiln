import {
  writable,
  derived,
  type Writable,
  type Readable,
  get,
} from "svelte/store"
import { client, base_url } from "$lib/api_client"
import { indexedDBStore } from "$lib/stores/index_db_store"
import type {
  KilnDocument,
  ModelProviderName,
  RunConfigProperties,
} from "$lib/types"
import { createKilnError, type KilnError } from "$lib/utils/error_handlers"

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
    use_full_documents: boolean
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
  useFullDocuments: boolean
  chunkSizeTokens: number | null
  chunkOverlapTokens: number | null
  runConfigProperties: RunConfigProperties
}

export type ChunkingConfig = {
  use_full_documents: boolean
  chunk_size_tokens: number | null
  chunk_overlap_tokens: number | null
}

export type QnaStore = {
  subscribe: (run: (s: QnASession) => void) => () => void
  status: Readable<"idle" | "running" | "done" | "error">
  progress: Readable<number>
  generatedCount: Readable<number>
  totalCount: Readable<number>
  error: Readable<string | null>
  generationErrors: Readable<KilnError[]>
  currentStep: Readable<StepNumber>
  maxStep: Readable<StepNumber>
  pendingSaveCount: Readable<number>
  saveAllStatus: Readable<{
    running: boolean
    completed: boolean
    errors: KilnError[]
    savedCount: number
  }>
  targetType: Readable<"all" | "document" | "part">
  targetDescription: Readable<string>

  extractorId: Writable<string | null>
  pairsPerPart: Writable<number>
  guidance: Writable<string>
  useFullDocuments: Writable<boolean>
  chunkSizeTokens: Writable<number | null>
  chunkOverlapTokens: Writable<number | null>

  init(defaultGuidance: string): Promise<void>
  destroy(): void
  setPendingTarget(target: GenerationTarget): void
  addDocuments(documents: KilnDocument[], tags: string[]): void
  setExtractor(id: string): void
  markExtractionComplete(id: string): void
  deleteDocument(id: string): void
  setSplits(splits: Record<string, number>): void
  removePair(documentId: string, partId: string, qaId: string): void
  removePart(documentId: string, partId: string): void
  setCurrentStep(step: StepNumber): void
  clearAll(defaultGuidance: string): void
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
      use_full_documents: true,
      chunk_size_tokens: null,
      chunk_overlap_tokens: null,
    },
    documents: [],
    splits: {},
  })

  // Progress and statuses
  const status = writable<"idle" | "running" | "done" | "error">("idle")
  const progress = writable<number>(0)
  const generatedCount = writable<number>(0)
  const totalCount = writable<number>(0)
  const error = writable<string | null>(null)
  const pendingTarget = writable<GenerationTarget>({ type: "all" })
  const manualStep = writable<StepNumber | null>(null)
  const _maxStep = writable<StepNumber>(1)

  // Save all
  const _saveAllRunning = writable<boolean>(false)
  const _saveAllCompleted = writable<boolean>(false)
  const _saveAllErrors = writable<KilnError[]>([])
  const _savedCount = writable<number>(0)

  // Generation errors
  const _generateErrors = writable<KilnError[]>([])

  // Generation config
  const extractorId = writable<string | null>(null)
  const pairsPerPart = writable<number>(5)
  const guidance = writable<string>("")
  const useFullDocuments = writable<boolean>(true)
  const chunkSizeTokens = writable<number | null>(null)
  const chunkOverlapTokens = writable<number | null>(null)

  let persistenceUnsubscribe: (() => void) | null = null
  let configUnsubscribes: Array<() => void> = []

  async function init(defaultGuidance: string): Promise<void> {
    /**
     * Load the state from IndexedDB and register subscriptions to the stores
     * and clean up on destroy.
     */
    const key = `qna_data_${projectId}_${taskId}`
    const { store, initialized } = indexedDBStore<QnASession>(key, {
      selected_tags: [],
      extractor_id: null,
      extraction_complete: false,
      generation_config: {
        pairs_per_part: 5,
        guidance: defaultGuidance,
        use_full_documents: true,
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
      extractorId.set(initialValue.extractor_id)
      pairsPerPart.set(initialValue.generation_config.pairs_per_part)
      guidance.set(initialValue.generation_config.guidance)
      useFullDocuments.set(initialValue.generation_config.use_full_documents)
      chunkSizeTokens.set(initialValue.generation_config.chunk_size_tokens)
      chunkOverlapTokens.set(
        initialValue.generation_config.chunk_overlap_tokens,
      )
    }

    persistenceUnsubscribe = _state.subscribe((value) => {
      ;(store as Writable<QnASession>).set(value)
    })

    configUnsubscribes.push(
      extractorId.subscribe((value) => {
        _state.update((s) => ({ ...s, extractor_id: value }))
      }),
    )
    configUnsubscribes.push(
      pairsPerPart.subscribe((value) => {
        _state.update((s) => ({
          ...s,
          generation_config: { ...s.generation_config, pairs_per_part: value },
        }))
      }),
    )
    configUnsubscribes.push(
      guidance.subscribe((value) => {
        _state.update((s) => ({
          ...s,
          generation_config: { ...s.generation_config, guidance: value },
        }))
      }),
    )
    configUnsubscribes.push(
      useFullDocuments.subscribe((value) => {
        _state.update((s) => ({
          ...s,
          generation_config: {
            ...s.generation_config,
            use_full_documents: value,
          },
        }))
      }),
    )
    configUnsubscribes.push(
      chunkSizeTokens.subscribe((value) => {
        _state.update((s) => ({
          ...s,
          generation_config: {
            ...s.generation_config,
            chunk_size_tokens: value,
          },
        }))
      }),
    )
    configUnsubscribes.push(
      chunkOverlapTokens.subscribe((value) => {
        _state.update((s) => ({
          ...s,
          generation_config: {
            ...s.generation_config,
            chunk_overlap_tokens: value,
          },
        }))
      }),
    )
  }

  function destroy(): void {
    if (persistenceUnsubscribe) {
      persistenceUnsubscribe()
      persistenceUnsubscribe = null
    }
    configUnsubscribes.forEach((unsub) => unsub())
    configUnsubscribes = []
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

  const targetType = derived(
    pendingTarget,
    ($target): "all" | "document" | "part" => $target.type,
  )

  const targetDescription = derived(
    [pendingTarget, _state],
    ([$target, $state]): string => {
      if ($target.type === "all") {
        return "all documents"
      } else if ($target.type === "document") {
        const doc = findDocumentById($state, $target.document_id)
        return doc ? doc.name : "selected document"
      } else if ($target.type === "part") {
        const doc = findDocumentById($state, $target.document_id)
        const partIdx = doc?.parts.findIndex((p) => p.id === $target.part_id)
        return doc && partIdx !== undefined && partIdx >= 0
          ? `${doc.name} - Part ${partIdx + 1}`
          : "selected part"
      }
      return "all documents"
    },
  )

  function setPendingTarget(target: GenerationTarget): void {
    pendingTarget.set(target)
  }

  function addDocuments(documents: KilnDocument[], tags: string[]): void {
    extractorId.set(null)
    _state.update((s) => {
      const newDocuments: QnADocumentNode[] = documents.map((doc) => {
        if (!doc.id) {
          throw new Error("Document ID is required")
        }

        return {
          id: doc.id,
          name: doc.friendly_name,
          tags: doc.tags || [],
          extracted: false,
          parts: [],
        }
      })
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
      const doc = findDocumentById(s, documentId)
      if (!doc) return s

      const part = findPartById(doc, partId)
      if (!part) return s

      const docs = s.documents.map((d) => {
        if (d.id !== documentId) return d
        return {
          ...d,
          parts: d.parts.map((p) => {
            if (p.id !== partId) return p
            return { ...p, qa_pairs: p.qa_pairs.filter((qa) => qa.id !== qaId) }
          }),
        }
      })
      return { ...s, documents: docs }
    })
  }

  function removePart(documentId: string, partId: string): void {
    _state.update((s) => {
      const doc = findDocumentById(s, documentId)
      if (!doc) return s

      const docs = s.documents.map((d) => {
        if (d.id !== documentId) return d
        return { ...d, parts: d.parts.filter((p) => p.id !== partId) }
      })
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
        use_full_documents: true,
        chunk_size_tokens: null,
        chunk_overlap_tokens: null,
      },
      documents: [],
      splits: {},
    }))
  }

  function findDocumentById(
    state: QnASession,
    docId: string,
  ): QnADocumentNode | null {
    return state.documents.find((d) => d.id === docId) ?? null
  }

  function findPartById(
    doc: QnADocumentNode,
    partId: string,
  ): QnADocPart | null {
    return doc.parts.find((p) => p.id === partId) ?? null
  }

  function findPairById(part: QnADocPart, pairId: string): QnAPair | null {
    return part.qa_pairs.find((qa) => qa.id === pairId) ?? null
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
    const { data, error } = await client.POST(
      "/api/projects/{project_id}/extractor_configs/{extractor_config_id}/documents/{document_id}/ephemeral_split",
      {
        params: {
          path: {
            project_id: projectId,
            extractor_config_id: extractorId,
            document_id: doc.id,
          },
        },
        body,
      },
    )
    if (error) {
      throw createKilnError(error)
    }

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

  function getTargetDocumentIds(
    state: QnASession,
    target: GenerationTarget,
  ): string[] {
    if (target.type === "all") {
      return state.documents.map((d) => d.id)
    } else if (target.type === "document") {
      const doc = findDocumentById(state, target.document_id)
      return doc ? [doc.id] : []
    } else if (target.type === "part") {
      const doc = findDocumentById(state, target.document_id)
      return doc ? [doc.id] : []
    }
    return []
  }

  async function ensureDocumentsChunked(
    documentIds: string[],
    extractorId: string | null,
    chunkSizeTokens: number | null,
    chunkOverlapTokens: number | null,
  ): Promise<void> {
    if (!extractorId) return

    const queue: number[] = []
    const state = get(_state)

    documentIds.forEach((docId) => {
      const docIdx = state.documents.findIndex((d) => d.id === docId)
      if (docIdx === -1) return

      const doc = state.documents[docIdx]
      const hasParts = doc.parts && doc.parts.length > 0
      const shouldReplace = hasParts && chunkSizeTokens !== null

      if (!hasParts || shouldReplace) {
        queue.push(docIdx)
      }
    })

    if (queue.length > 0) {
      await runChunkingQueue(
        queue,
        extractorId,
        chunkSizeTokens,
        chunkOverlapTokens,
        5,
      )
    }
  }

  async function callGenerateQnAAPI(
    documentId: string,
    partText: string,
    pairsPerPart: number,
    guidance: string,
    runConfigProperties: RunConfigProperties,
  ): Promise<QnAPair[]> {
    const { data, error: apiError } = await client.POST(
      "/api/projects/{project_id}/tasks/{task_id}/generate_qna",
      {
        body: {
          document_id: documentId,
          part_text: [partText],
          num_samples: pairsPerPart,
          run_config_properties: runConfigProperties,
          guidance: guidance || null,
          tags: null,
        },
        params: { path: { project_id: projectId, task_id: taskId } },
      },
    )
    if (apiError) throw apiError

    const outputText = data.output.output
    const response = JSON.parse(outputText) as {
      generated_qna_pairs?: Array<{ question: unknown; answer: unknown }>
    }
    const generated = Array.isArray(response.generated_qna_pairs)
      ? response.generated_qna_pairs
      : []

    const modelProvider = runConfigProperties.model_provider_name
    const modelName = runConfigProperties.model_name

    return generated.map((qa) => ({
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
  }

  type PartReference = { documentId: string; partId: string }

  function getPartsForTargetById(
    state: QnASession,
    target: GenerationTarget,
  ): PartReference[] {
    const parts: PartReference[] = []

    if (target.type === "all") {
      state.documents.forEach((doc) => {
        doc.parts.forEach((part) => {
          parts.push({ documentId: doc.id, partId: part.id })
        })
      })
    } else if (target.type === "document") {
      const doc = findDocumentById(state, target.document_id)
      if (doc) {
        doc.parts.forEach((part) => {
          parts.push({ documentId: doc.id, partId: part.id })
        })
      }
    } else if (target.type === "part") {
      const doc = findDocumentById(state, target.document_id)
      if (doc) {
        const part = findPartById(doc, target.part_id)
        if (part) {
          parts.push({ documentId: doc.id, partId: part.id })
        }
      }
    }

    return parts
  }

  async function generateQnAPairsForParts(
    parts: PartReference[],
    pairsPerPart: number,
    guidance: string,
    runConfigProperties: RunConfigProperties,
    useFullDocuments: boolean,
    chunkSizeTokens: number | null,
    chunkOverlapTokens: number | null,
  ): Promise<void> {
    const total = parts.length * pairsPerPart
    totalCount.set(total)
    generatedCount.set(0)

    for (const { documentId, partId } of parts) {
      const state = get(_state)
      const doc = findDocumentById(state, documentId)
      if (!doc) {
        continue
      }

      const part = findPartById(doc, partId)
      if (!part) {
        continue
      }

      try {
        const newPairs = await callGenerateQnAAPI(
          documentId,
          part.text_preview,
          pairsPerPart,
          guidance,
          runConfigProperties,
        )

        _state.update((s) => {
          const docs = s.documents.map((d) => {
            if (d.id !== documentId) return d
            return {
              ...d,
              parts: d.parts.map((p) => {
                if (p.id !== partId) return p
                return { ...p, qa_pairs: [...p.qa_pairs, ...newPairs] }
              }),
            }
          })
          return {
            ...s,
            generation_config: {
              pairs_per_part: pairsPerPart,
              guidance,
              use_full_documents: useFullDocuments,
              chunk_size_tokens: useFullDocuments ? null : chunkSizeTokens,
              chunk_overlap_tokens: useFullDocuments
                ? null
                : chunkOverlapTokens,
            },
            documents: docs,
          }
        })

        generatedCount.update(
          (prevCount: number) => prevCount + newPairs.length,
        )
      } catch (e) {
        const kilnError = createKilnError(e)
        const docName = doc.name || "Unknown document"
        const partIndex =
          doc.parts.findIndex((p) => p.id === partId) + 1 || "Unknown"
        kilnError.message = `${docName} - Part ${partIndex}: ${kilnError.message}`
        _generateErrors.update((arr) => [...arr, kilnError])
      }

      progress.set(Math.round((get(generatedCount) / total) * 100))
    }
  }

  async function generate({
    pairsPerPart,
    guidance,
    runConfigProperties,
    useFullDocuments,
    chunkSizeTokens,
    chunkOverlapTokens,
  }: GenerationParams): Promise<void> {
    status.set("running")
    progress.set(0)
    generatedCount.set(0)
    totalCount.set(0)
    error.set(null)
    _generateErrors.set([])

    try {
      const state = get(_state)
      const targetSel = get(pendingTarget)

      const documentIds = getTargetDocumentIds(state, targetSel)

      if (targetSel.type === "all") {
        _state.update((s) => ({
          ...s,
          documents: s.documents.map((doc) => {
            // we clear the parts for all documents because corpus-wide regeneration can change the chunking
            // and result in totally different chunks
            if (documentIds.includes(doc.id)) {
              return { ...doc, parts: [] }
            }
            return doc
          }),
        }))
      }

      if (targetSel.type === "all" || targetSel.type === "document") {
        await ensureDocumentsChunked(
          documentIds,
          state.extractor_id,
          chunkSizeTokens,
          chunkOverlapTokens,
        )
      }

      const targetParts = getPartsForTargetById(get(_state), targetSel)

      await generateQnAPairsForParts(
        targetParts,
        pairsPerPart,
        guidance,
        runConfigProperties,
        useFullDocuments,
        chunkSizeTokens,
        chunkOverlapTokens,
      )

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

  type PairReference = {
    documentId: string
    partId: string
    pairId: string
  }

  function buildSaveQueue(state: QnASession): PairReference[] {
    const queue: PairReference[] = []
    state.documents.forEach((doc) => {
      doc.parts.forEach((part) => {
        part.qa_pairs.forEach((pair) => {
          if (!pair.saved_id) {
            queue.push({
              documentId: doc.id,
              partId: part.id,
              pairId: pair.id,
            })
          }
        })
      })
    })
    return queue
  }

  function calculateSplitTag(
    splits: Record<string, number>,
  ): string | undefined {
    const keys = Object.keys(splits)
    if (keys.length === 0) return undefined

    const r = Math.random()
    let acc = 0
    for (const k of keys) {
      acc += splits[k]
      if (r <= acc) return k
    }
    return keys[0]
  }

  async function saveSinglePair(
    ref: PairReference,
    sessionId: string,
  ): Promise<void> {
    const state = get(_state)
    const doc = findDocumentById(state, ref.documentId)
    if (!doc) return

    const part = findPartById(doc, ref.partId)
    if (!part) return

    const pair = findPairById(part, ref.pairId)
    if (!pair) return

    if (!pair.model_name || !pair.model_provider) {
      throw new Error("Model name and provider are required")
    }

    const splitTag = calculateSplitTag(state.splits)

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
    if (apiError || !data || !data.id)
      throw apiError || new Error("Save failed")

    const savedId = data.id
    _state.update((s) => {
      const docs = s.documents.map((d) => {
        if (d.id !== ref.documentId) return d
        return {
          ...d,
          parts: d.parts.map((p) => {
            if (p.id !== ref.partId) return p
            return {
              ...p,
              qa_pairs: p.qa_pairs.map((qa) => {
                if (qa.id !== ref.pairId) return qa
                return { ...qa, saved_id: savedId }
              }),
            }
          }),
        }
      })
      return { ...s, documents: docs }
    })
    _savedCount.update((c) => c + 1)
  }

  async function saveAll(sessionId: string): Promise<void> {
    try {
      _saveAllRunning.set(true)
      _saveAllCompleted.set(false)
      _saveAllErrors.set([])
      _savedCount.set(0)

      const state = get(_state)
      const queue = buildSaveQueue(state)

      for (const ref of queue) {
        try {
          await saveSinglePair(ref, sessionId)
        } catch (e) {
          _saveAllErrors.update((arr) => [...arr, createKilnError(e)])
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
    generatedCount,
    totalCount,
    error,
    generationErrors: _generateErrors,
    currentStep,
    maxStep,
    pendingSaveCount,
    saveAllStatus,
    targetType,
    targetDescription,
    extractorId,
    pairsPerPart,
    guidance,
    useFullDocuments,
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
    generate,
    saveAll,
  }
}
