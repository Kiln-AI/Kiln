// @vitest-environment jsdom
import { describe, it, expect, afterEach } from "vitest"
import { render, cleanup } from "@testing-library/svelte"
import ErrorDetailsBlock from "./error_details_block.svelte"

afterEach(() => cleanup())

const PROPS = {
  title: "Can't Reach OpenEnv",
  error_messages: ["All connection attempts failed"],
  troubleshooting_steps: ["Check the OpenEnv server is running."],
}

describe("error_details_block width", () => {
  it("is centred at 600px by default", () => {
    const { container } = render(ErrorDetailsBlock, { props: PROPS })
    const block = container.firstElementChild as HTMLElement
    expect(block.className).toContain("max-w-[600px]")
    expect(block.className).toContain("mx-auto")
  })

  it("spans its container when full_width is set", () => {
    const { container } = render(ErrorDetailsBlock, {
      props: { ...PROPS, full_width: true },
    })
    const block = container.firstElementChild as HTMLElement
    expect(block.className).not.toContain("max-w-[600px]")
    expect(block.className).not.toContain("mx-auto")
    expect(block.className).toContain("border")
    expect(block.textContent).toContain("Can't Reach OpenEnv")
  })
})
