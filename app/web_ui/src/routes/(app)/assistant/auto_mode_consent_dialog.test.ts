// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest"
import { render, cleanup } from "@testing-library/svelte"
import { tick } from "svelte"
import type { AutoModeConsentRequiredPayload } from "$lib/chat/streaming_chat"

vi.mock("posthog-js", () => ({
  default: { capture: vi.fn() },
}))

const AutoModeConsentDialog = (
  await import("./auto_mode_consent_dialog.svelte")
).default

// jsdom doesn't implement HTMLDialogElement.showModal/close; emulate them.
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
})

function payload(
  overrides: Partial<AutoModeConsentRequiredPayload> = {},
): AutoModeConsentRequiredPayload {
  return {
    trigger: "enable_auto_mode",
    gatingToolCallId: "call_1",
    reason: null,
    spawn: null,
    siblingToolCalls: [],
    ...overrides,
  }
}

function spawnPayload(): AutoModeConsentRequiredPayload {
  return payload({
    trigger: "spawn_subagent",
    gatingToolCallId: "call_spawn",
    spawn: { agentType: "general", name: "Helper", prompt: "dig into logs" },
  })
}

describe("AutoModeConsentDialog", () => {
  it("resolves true when the user turns on auto mode", async () => {
    const { component, container } = render(AutoModeConsentDialog)
    const promise = component.prompt(payload())
    await tick()

    // The primary button carries the "Turn on auto mode" label.
    const buttons = Array.from(container.querySelectorAll("button"))
    const turnOn = buttons.find((b) =>
      b.textContent?.includes("Turn on auto mode"),
    )
    expect(turnOn).toBeTruthy()
    turnOn!.click()

    await expect(promise).resolves.toBe(true)
  })

  it("resolves false when dismissed (close event)", async () => {
    const { component, container } = render(AutoModeConsentDialog)
    const promise = component.prompt(payload())
    await tick()

    const dialog = container.querySelector("dialog") as HTMLDialogElement
    dialog.dispatchEvent(new Event("close"))

    await expect(promise).resolves.toBe(false)
  })

  it("renders the model reason callout only when a reason is present", async () => {
    const { component, container } = render(AutoModeConsentDialog)
    component.prompt(payload({ reason: "finish the eval sweep" }))
    await tick()
    expect(container.textContent).toContain(
      "The assistant suggests auto mode to: finish the eval sweep",
    )
  })

  it("omits the reason callout when no reason is supplied", async () => {
    const { component, container } = render(AutoModeConsentDialog)
    component.prompt(payload({ reason: null }))
    await tick()
    expect(container.textContent).not.toContain(
      "The assistant suggests auto mode to:",
    )
  })

  it("renders the spawn callout naming the sub-agent for the spawn variant", async () => {
    const { component, container } = render(AutoModeConsentDialog)
    component.prompt(spawnPayload())
    await tick()
    expect(container.textContent).toContain(
      "The assistant wants to spawn a sub-agent",
    )
    expect(container.textContent).toContain("Helper")
    expect(container.textContent).toContain("general")
    // The decision framing is unchanged: turning on auto mode IS the consent.
    const buttons = Array.from(container.querySelectorAll("button"))
    expect(
      buttons.some((b) => b.textContent?.includes("Turn on auto mode")),
    ).toBe(true)
  })

  it("omits the spawn callout for the enable variant and the manual prompt", async () => {
    const { component, container } = render(AutoModeConsentDialog)
    component.prompt(payload())
    await tick()
    expect(container.textContent).not.toContain(
      "The assistant wants to spawn a sub-agent",
    )
  })

  it("spawn variant accept resolves true (same decision flow)", async () => {
    const { component, container } = render(AutoModeConsentDialog)
    const promise = component.prompt(spawnPayload())
    await tick()
    const buttons = Array.from(container.querySelectorAll("button"))
    const turnOn = buttons.find((b) =>
      b.textContent?.includes("Turn on auto mode"),
    )
    turnOn!.click()
    await expect(promise).resolves.toBe(true)
  })
})
