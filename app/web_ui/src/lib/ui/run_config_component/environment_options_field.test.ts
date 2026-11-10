// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { render, cleanup } from "@testing-library/svelte"
import { tick } from "svelte"
import type { OpenEnvServer, RunOpenEnvServer } from "$lib/types"

const lookup = vi.fn<[string, string, string[]], Promise<RunOpenEnvServer>>()
vi.mock("$lib/api/openenv_server_api", () => ({
  lookup_run_openenv_server: (...args: [string, string, string[]]) =>
    lookup(...args),
}))

vi.mock("$lib/utils/form_element.svelte", async () => {
  const { default: Stub } = await import(
    "./__tests__/form_element_props_stub.svelte"
  )
  return { default: Stub }
})

const EnvironmentOptionsField = (
  await import("./environment_options_field.svelte")
).default

const OPENENV_TOOL = "kiln_tool::openenv::openenv_1::list_items"

const ACME: OpenEnvServer = {
  id: "openenv_1",
  name: "Acme",
  named_reset_kwargs: [
    { name: "Acme Tech", reset_kwargs: { company: "acme", role: "tech" } },
    {
      name: "Acme Manager",
      reset_kwargs: { company: "acme", role: "manager" },
    },
  ],
}

beforeEach(() => {
  vi.useFakeTimers()
  lookup.mockReset()
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

function render_field(tool_ids: string[]) {
  return render(EnvironmentOptionsField, {
    props: { project_id: "p1", task_id: "t1", tool_ids },
  })
}

async function settle() {
  await vi.advanceTimersByTimeAsync(250)
  await tick()
}

function field_props(container: HTMLElement): DOMStringMap | null {
  const el = container.querySelector<HTMLElement>(
    '[data-testid="form-element-props"]',
  )
  return el ? el.dataset : null
}

describe("EnvironmentOptionsField", () => {
  it("stays hidden, without a lookup, when there are no tools", async () => {
    const { container, component } = render_field([])
    await settle()
    expect(lookup).not.toHaveBeenCalled()
    expect(container.innerHTML.trim()).toBe("")
    expect(await component.get_openenv_reset_kwargs()).toBeNull()
  })

  it("stays hidden when the tools reach no OpenEnv", async () => {
    lookup.mockResolvedValue({ openenv_server: null, error: null })
    const { container, component } = render_field(["mcp::remote::s::search"])
    await settle()
    expect(lookup).toHaveBeenCalledWith("p1", "t1", ["mcp::remote::s::search"])
    expect(field_props(container)).toBeNull()
    expect(await component.get_openenv_reset_kwargs()).toBeNull()
  })

  it("shows the error line in place of the dropdown", async () => {
    const message =
      "Your tools use more than one OpenEnv (Acme, Beta). A run can only use one."
    lookup.mockResolvedValue({ openenv_server: null, error: message })
    const { container, component } = render_field([OPENENV_TOOL])
    await settle()
    const props = field_props(container)
    expect(props?.inputType).toBe("header_only")
    expect(props?.label).toBe("Environment Options")
    // Shown once, in the error line, not also as the label's error icon.
    expect(props?.errorMessage).toBeUndefined()
    expect(container.querySelector(".text-error")?.textContent).toBe(message)
    expect(await component.get_openenv_reset_kwargs()).toBeNull()
  })

  it("shows a failed lookup as the error line, and refuses the run", async () => {
    lookup.mockRejectedValue(new Error("Network down"))
    const { container, component } = render_field([OPENENV_TOOL])
    await settle()
    expect(container.querySelector(".text-error")?.textContent).toContain(
      "Network down",
    )
    await expect(component.get_openenv_reset_kwargs()).rejects.toThrow(
      "Network down",
    )
    // Run retries the lookup once before refusing.
    expect(lookup).toHaveBeenCalledTimes(2)
  })

  it("recovers when the retried lookup succeeds", async () => {
    lookup
      .mockRejectedValueOnce(new Error("Network down"))
      .mockResolvedValueOnce({ openenv_server: ACME, error: null })
    const { container, component } = render_field([OPENENV_TOOL])
    await settle()
    expect(await component.get_openenv_reset_kwargs()).toEqual({
      company: "acme",
      role: "tech",
    })
    await tick()
    expect(container.querySelector(".text-error")).toBeNull()
  })

  it("shows the empty state, linking the OpenEnv's page, with no options", async () => {
    lookup.mockResolvedValue({
      openenv_server: { ...ACME, named_reset_kwargs: [] },
      error: null,
    })
    const { container, component } = render_field([OPENENV_TOOL])
    await settle()
    const props = field_props(container)
    expect(props?.inputType).toBe("fancy_select")
    expect(JSON.parse(props?.optionValues ?? "")).toEqual([])
    expect(props?.emptyStateMessage).toBe("No Environment Options")
    expect(props?.emptyStateSubtitle).toBe("Add Environment Options")
    expect(props?.emptyStateLink).toBe("/tools/p1/openenv_servers/openenv_1")
    expect(await component.get_openenv_reset_kwargs()).toBeNull()
  })

  it("lists the options in order, with the first selected", async () => {
    lookup.mockResolvedValue({ openenv_server: ACME, error: null })
    const { container, component } = render_field([OPENENV_TOOL])
    await settle()
    const props = field_props(container)
    expect(props?.inputType).toBe("fancy_select")
    expect(JSON.parse(props?.optionValues ?? "")).toEqual([
      "Acme Tech",
      "Acme Manager",
    ])
    expect(JSON.parse(props?.optionDescriptions ?? "")[0]).toBe(
      '{\n  "company": "acme",\n  "role": "tech"\n}',
    )
    expect(JSON.parse(props?.value ?? "")).toBe("Acme Tech")
    expect(await component.get_openenv_reset_kwargs()).toEqual({
      company: "acme",
      role: "tech",
    })
  })

  it("looks up once for a burst of tool changes", async () => {
    lookup.mockResolvedValue({ openenv_server: ACME, error: null })
    const { component } = render_field(["a"])
    await vi.advanceTimersByTimeAsync(100)
    await component.$set({ tool_ids: ["a", "b"] })
    await vi.advanceTimersByTimeAsync(100)
    await component.$set({ tool_ids: ["a", "b", OPENENV_TOOL] })
    await settle()
    expect(lookup).toHaveBeenCalledTimes(1)
    expect(lookup).toHaveBeenCalledWith("p1", "t1", ["a", "b", OPENENV_TOOL])
  })

  it("doesn't look up again for the same tools", async () => {
    lookup.mockResolvedValue({ openenv_server: ACME, error: null })
    const { component } = render_field([OPENENV_TOOL])
    await settle()
    await component.$set({ tool_ids: [OPENENV_TOOL] })
    await settle()
    expect(lookup).toHaveBeenCalledTimes(1)
  })

  it("ignores a reply that arrives after a newer one", async () => {
    let resolve_first: (value: RunOpenEnvServer) => void = () => {}
    lookup
      .mockImplementationOnce(
        () => new Promise((resolve) => (resolve_first = resolve)),
      )
      .mockResolvedValueOnce({ openenv_server: null, error: null })
    const { container, component } = render_field([OPENENV_TOOL])
    await settle()
    await component.$set({ tool_ids: ["mcp::remote::s::search"] })
    await settle()
    resolve_first({ openenv_server: ACME, error: null })
    await tick()
    expect(field_props(container)).toBeNull()
  })

  it("waits for a pending lookup before giving the reset arguments", async () => {
    lookup.mockResolvedValue({ openenv_server: ACME, error: null })
    const { component } = render_field([OPENENV_TOOL])
    expect(lookup).not.toHaveBeenCalled()
    expect(await component.get_openenv_reset_kwargs()).toEqual({
      company: "acme",
      role: "tech",
    })
    expect(lookup).toHaveBeenCalledTimes(1)
  })
})
