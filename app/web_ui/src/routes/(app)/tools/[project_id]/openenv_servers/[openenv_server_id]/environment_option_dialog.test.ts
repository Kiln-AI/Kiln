// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { render, cleanup, fireEvent, waitFor } from "@testing-library/svelte"
import type { NamedResetKwargs } from "$lib/types"

const mock_get = vi.fn()

vi.mock("$lib/api_client", () => ({
  client: { GET: (...args: unknown[]) => mock_get(...args) },
}))

// The schema form registers its fields from onMount.
vi.mock("svelte", async (importOriginal) =>
  (await import("$lib/test_support/browser_svelte")).browser_svelte(
    importOriginal,
  ),
)

vi.mock("$lib/components/code_editor.svelte", async () => ({
  default: (
    await import("$lib/components/eval_types/__tests__/code_editor_stub.svelte")
  ).default,
}))

const EnvironmentOptionDialog = (
  await import("./environment_option_dialog.svelte")
).default

const RESET_SCHEMA = {
  type: "object",
  properties: {
    company: { type: "string", title: "Company" },
    seed: { anyOf: [{ type: "integer" }, { type: "null" }], title: "Seed" },
  },
}

const ACME: NamedResetKwargs = {
  name: "Acme",
  reset_kwargs: { company: "acme" },
}
const ODD: NamedResetKwargs = { name: "Odd", reset_kwargs: { foo: 1 } }

beforeEach(() => {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  ;(HTMLDialogElement.prototype as any).showModal = function (
    this: HTMLDialogElement,
  ) {
    this.setAttribute("open", "")
  }
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  ;(HTMLDialogElement.prototype as any).close = function (
    this: HTMLDialogElement,
  ) {
    this.removeAttribute("open")
  }
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

function serve_schema(reset_schema: unknown) {
  mock_get.mockResolvedValue({ data: { reset_schema }, error: undefined })
}

function render_dialog(options: NamedResetKwargs[] = [ACME, ODD]) {
  const save = vi.fn().mockResolvedValue(undefined)
  const { component, container } = render(EnvironmentOptionDialog, {
    props: { project_id: "p1", openenv_server_id: "e1", options, save },
  })
  return { component, container, save }
}

function editor(container: HTMLElement): HTMLTextAreaElement | null {
  return container.querySelector('[data-testid="code-editor-textarea"]')
}

function form_field(container: HTMLElement, title: string) {
  return container.querySelector<HTMLTextAreaElement | HTMLInputElement>(
    `[aria-label="${title}"]`,
  )
}

function toggle(container: HTMLElement, label: string) {
  return Array.from(container.querySelectorAll("button")).find(
    (b) => b.textContent?.trim() === label,
  )
}

async function submit(container: HTMLElement) {
  await fireEvent.click(
    container.querySelector('button[type="submit"]') as HTMLButtonElement,
  )
}

describe("EnvironmentOptionDialog", () => {
  it("is the JSON editor with no toggle when the server has no schema", async () => {
    serve_schema(null)
    const { component, container } = render_dialog()
    component.show_add()
    await waitFor(() => expect(mock_get).toHaveBeenCalled())
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(editor(container)).not.toBeNull()
    expect(toggle(container, "Raw JSON")).toBeUndefined()
    expect(toggle(container, "Form")).toBeUndefined()
    expect(container.textContent).toContain(
      "Passed to the OpenEnv's reset(). Which keys exist depends on the server.",
    )
  })

  it("keeps the JSON editor when the schema can't be read", async () => {
    mock_get.mockResolvedValue({ data: undefined, error: { message: "down" } })
    const { component, container } = render_dialog()
    component.show_add()
    await waitFor(() => expect(mock_get).toHaveBeenCalled())
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(editor(container)).not.toBeNull()
    expect(toggle(container, "Form")).toBeUndefined()
  })

  it("shows the schema form for a new option and saves only filled fields", async () => {
    serve_schema(RESET_SCHEMA)
    const { component, container, save } = render_dialog()
    component.show_add()
    await waitFor(() => expect(form_field(container, "Company")).not.toBeNull())
    expect(editor(container)).toBeNull()
    expect(toggle(container, "Raw JSON")).toBeDefined()
    expect(container.textContent).toContain(
      "From the OpenEnv server's reset schema.",
    )

    await fireEvent.input(
      container.querySelector("#environment_option_name")!,
      {
        target: { value: "Beta" },
      },
    )
    await fireEvent.input(form_field(container, "Company")!, {
      target: { value: "beta" },
    })
    await submit(container)

    await waitFor(() => expect(save).toHaveBeenCalledTimes(1))
    expect(save).toHaveBeenCalledWith([
      ACME,
      ODD,
      { name: "Beta", reset_kwargs: { company: "beta" } },
    ])
  })

  it("opens an edit that fits on the form, prefilled, and round trips Raw JSON", async () => {
    serve_schema(RESET_SCHEMA)
    const { component, container } = render_dialog()
    component.show_edit(0)
    await waitFor(() =>
      expect(form_field(container, "Company")?.value).toBe("acme"),
    )

    await fireEvent.click(toggle(container, "Raw JSON")!)
    await waitFor(() => expect(editor(container)).not.toBeNull())
    expect(editor(container)!.value).toBe('{\n  "company": "acme"\n}')

    await fireEvent.input(editor(container)!, {
      target: { value: '{"company": "beta", "seed": 4}' },
    })
    await fireEvent.click(toggle(container, "Form")!)
    await waitFor(() =>
      expect(form_field(container, "Company")?.value).toBe("beta"),
    )
    expect(form_field(container, "Seed")?.value).toBe("4")
  })

  it("opens an edit the form can't show on Raw JSON, and says why it can't switch", async () => {
    serve_schema(RESET_SCHEMA)
    const { component, container } = render_dialog()
    component.show_edit(1)
    await waitFor(() => expect(toggle(container, "Form")).toBeDefined())
    expect(editor(container)!.value).toBe('{\n  "foo": 1\n}')

    await fireEvent.click(toggle(container, "Form")!)
    await waitFor(() =>
      expect(container.textContent).toContain(
        "The form can't show these reset arguments: unknown field 'foo'. Edit them as JSON.",
      ),
    )
    expect(editor(container)).not.toBeNull()
  })

  it("stays on the JSON editor when the user types before the schema loads", async () => {
    let resolve_schema: (value: unknown) => void = () => {}
    mock_get.mockReturnValue(
      new Promise((resolve) => {
        resolve_schema = resolve
      }),
    )
    const { component, container } = render_dialog()
    component.show_add()
    await waitFor(() => expect(editor(container)).not.toBeNull())
    await fireEvent.input(editor(container)!, {
      target: { value: '{"company": "acme"}' },
    })
    resolve_schema({ data: { reset_schema: RESET_SCHEMA }, error: undefined })
    await waitFor(() => expect(toggle(container, "Form")).toBeDefined())
    expect(editor(container)!.value).toBe('{"company": "acme"}')
  })
})
