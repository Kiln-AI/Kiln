// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { render, cleanup, fireEvent, waitFor } from "@testing-library/svelte"
import { tick } from "svelte"
import * as svelteMod from "svelte"
import type { RagConfigWithSubConfigs } from "$lib/types"

// ---------------------------------------------------------------------------
// Hoisted mocks (must exist before the form module import). onMount does not
// auto-fire in this test setup (SSR-mode resolution), so — following the
// repo convention (see eval_config_builder_form_scope.test.ts) — we spy on
// `onMount`, collect the callbacks, and run them by hand after render.
// ---------------------------------------------------------------------------
const { mockPageStore, mockGet, mockPost, onMountCbs } = vi.hoisted(() => {
  const value = { params: { project_id: "proj1" } }
  const mockPageStore = {
    subscribe(fn: (v: typeof value) => void) {
      fn(value)
      return () => {}
    },
  }
  return {
    mockPageStore,
    mockGet: vi.fn(),
    mockPost: vi.fn(),
    onMountCbs: [] as Array<() => unknown>,
  }
})

vi.mock("$app/stores", () => ({ page: mockPageStore }))
vi.mock("$app/navigation", () => ({
  goto: vi.fn(),
  beforeNavigate: vi.fn(),
}))

vi.mock("$lib/api_client", () => ({
  client: {
    GET: (...args: unknown[]) => mockGet(...args),
    POST: (...args: unknown[]) => mockPost(...args),
  },
}))

vi.mock("$lib/stores", () => ({
  load_available_embedding_models: vi.fn().mockResolvedValue(undefined),
  load_available_reranker_models: vi.fn().mockResolvedValue(undefined),
  uncache_available_tools: vi.fn(),
}))

vi.mock("posthog-js", () => ({ default: { capture: vi.fn() } }))

// build_rag_config_sub_configs performs network work when saving from a
// template; stub it to return fixed ids so the template create path reaches POST.
vi.mock("../add_search_tool/rag_config_templates", () => ({
  build_rag_config_sub_configs: vi.fn().mockResolvedValue({
    extractor_config_id: "ex1",
    chunker_config_id: "ch1",
    embedding_config_id: "em1",
    vector_store_config_id: "vs1",
  }),
}))

// Stub the heavy child components with a single no-op stub. The dynamic import
// is inlined in each factory because vi.mock is hoisted above any top-level
// declaration (a shared const would hit the TDZ when the factory runs).
vi.mock("./create_chunker_dialog.svelte", async () => ({
  default: (await import("./__tests__/child_stub.svelte")).default,
}))
vi.mock("./create_embedding_dialog.svelte", async () => ({
  default: (await import("./__tests__/child_stub.svelte")).default,
}))
vi.mock("./create_vector_store_dialog.svelte", async () => ({
  default: (await import("./__tests__/child_stub.svelte")).default,
}))
vi.mock("./create_extractor_dialog.svelte", async () => ({
  default: (await import("./__tests__/child_stub.svelte")).default,
}))
vi.mock("./create_reranker_dialog.svelte", async () => ({
  default: (await import("./__tests__/child_stub.svelte")).default,
}))
vi.mock("./tag_selector.svelte", async () => ({
  default: (await import("./__tests__/child_stub.svelte")).default,
}))
vi.mock("./template_property_overview.svelte", async () => ({
  default: (await import("./__tests__/child_stub.svelte")).default,
}))

import EditRagConfigForm from "./edit_rag_config_form.svelte"

afterEach(() => {
  cleanup()
  // clearAllMocks (not restoreAllMocks) so the module-mock implementations set
  // in the vi.mock factories (e.g. build_rag_config_sub_configs' resolved value)
  // survive across tests; the onMount spy is restored inside renderForm.
  vi.clearAllMocks()
})

beforeEach(() => {
  mockGet.mockReset()
  mockPost.mockReset()
  // Sub-config list loads return empty; the form only needs the selected ids
  // (prefilled from initial_rag_config on clone) to reach the POST.
  mockGet.mockResolvedValue({ data: [], error: null })
  mockPost.mockResolvedValue({ data: { id: "new-rag-id" }, error: null })
})

// Render the form and run its onMount by hand (see note above).
async function renderForm(
  props: Record<string, unknown>,
): Promise<HTMLElement> {
  onMountCbs.length = 0
  const spy = vi
    .spyOn(svelteMod, "onMount")
    .mockImplementation((fn: () => unknown) => {
      onMountCbs.push(fn)
    })
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const { container } = render(EditRagConfigForm as any, { props })
  spy.mockRestore()
  for (const cb of onMountCbs) await cb()
  await tick()
  return container
}

function button_with_text(container: HTMLElement, text: string): HTMLElement {
  const btn = Array.from(container.querySelectorAll("button")).find((b) =>
    b.textContent?.includes(text),
  )
  if (!btn) throw new Error(`button "${text}" not found`)
  return btn as HTMLElement
}

async function set_input(container: HTMLElement, id: string, value: string) {
  const el = container.querySelector(`#${id}`) as
    | HTMLInputElement
    | HTMLTextAreaElement
  await fireEvent.input(el, { target: { value } })
  await tick()
}

// A fully-populated source config, as the clone route hands to the form.
function clone_source(id: string): RagConfigWithSubConfigs {
  return {
    id,
    name: "Source RAG",
    description: "desc",
    tool_name: "search_docs",
    tool_description: "Search the docs.",
    extractor_config: { id: "ex-src" },
    chunker_config: { id: "ch-src" },
    embedding_config: { id: "em-src" },
    vector_store_config: { id: "vs-src" },
    reranker_config: null,
    tags: [],
  } as unknown as RagConfigWithSubConfigs
}

describe("EditRagConfigForm provenance stamping", () => {
  it("clone create stamps derived_from_ids with the source rag config id", async () => {
    const container = await renderForm({
      initial_rag_config: clone_source("src-rag-id"),
    })

    // onMount prefilled the form from the source (tool fields + selected ids).
    expect(
      (container.querySelector("#tool_name") as HTMLInputElement).value,
    ).toBe("search_docs")

    await fireEvent.click(button_with_text(container, "Create Search Tool"))

    await waitFor(() => expect(mockPost).toHaveBeenCalled())
    const body = mockPost.mock.calls[0][1].body
    expect(body.provenance).toEqual({
      origin: "human",
      derived_from_ids: ["src-rag-id"],
    })
  })

  it("template fresh create sends human-origin provenance with no parent", async () => {
    const container = await renderForm({
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      template: { name: "Template A", rag_config_name: "template-a" } as any,
    })

    // tool_name / tool_description are the only required inputs on the template
    // path (sub-configs are built by the stubbed builder).
    await set_input(container, "tool_name", "search_docs")
    await set_input(container, "tool_description", "Search the docs.")

    await fireEvent.click(button_with_text(container, "Create Search Tool"))

    await waitFor(() => expect(mockPost).toHaveBeenCalled())
    const body = mockPost.mock.calls[0][1].body
    expect(body.provenance).toEqual({ origin: "human" })
  })
})
