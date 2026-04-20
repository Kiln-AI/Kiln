// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from "vitest"
import { cleanup, render, screen } from "@testing-library/svelte"
import OAuthInstallStep from "./oauth_install_step.svelte"
import { INITIAL_STATE } from "./oauth_with_install"
import type { OAuthWithInstallState } from "./oauth_with_install"

function make_state(
  overrides: Partial<OAuthWithInstallState> = {},
): OAuthWithInstallState {
  return { ...INITIAL_STATE, needs_install: true, ...overrides }
}

const noop = () => {}
const noop_async = async () => {}

describe("OAuthInstallStep", () => {
  afterEach(() => cleanup())

  it("renders authorized checkmark and install button", () => {
    const { container } = render(OAuthInstallStep, {
      props: {
        state: make_state(),
        open_install: noop,
        verify_access: noop_async,
        reset: noop,
      },
    })
    expect(container.querySelector(".bg-success\\/10")).not.toBeNull()
    expect(screen.getByText("Step 1: Authorized")).not.toBeNull()
    expect(screen.getByText("Step 2: Install App on Repository")).not.toBeNull()
    expect(screen.getByText("Install Kiln Sync on GitHub")).not.toBeNull()
    expect(screen.getByText("Verify Access")).not.toBeNull()
    expect(screen.getByText("Start over")).not.toBeNull()
  })

  it("renders compact variant with shorter labels", () => {
    render(OAuthInstallStep, {
      props: {
        state: make_state(),
        open_install: noop,
        verify_access: noop_async,
        reset: noop,
        compact: true,
      },
    })
    expect(screen.getByText("Authorized")).not.toBeNull()
    expect(screen.getByText("Install App on Repository")).not.toBeNull()
  })

  it("shows retry button after install clicked", () => {
    render(OAuthInstallStep, {
      props: {
        state: make_state({ install_clicked: true }),
        open_install: noop,
        verify_access: noop_async,
        reset: noop,
      },
    })
    expect(screen.getByText("Retry Install on GitHub")).not.toBeNull()
  })

  it("shows spinner when checking access", () => {
    const { container } = render(OAuthInstallStep, {
      props: {
        state: make_state({ checking_access: true }),
        open_install: noop,
        verify_access: noop_async,
        reset: noop,
      },
    })
    expect(container.querySelector(".loading-spinner")).not.toBeNull()
    const verify_btn = screen.getByText("Verify Access").closest("button")
    expect(verify_btn?.disabled).toBe(true)
  })

  it("shows error warning when oauth_error is set", () => {
    render(OAuthInstallStep, {
      props: {
        state: make_state({ oauth_error: "Something went wrong" }),
        open_install: noop,
        verify_access: noop_async,
        reset: noop,
      },
    })
    expect(screen.getByText("Something went wrong")).not.toBeNull()
  })

  it("calls open_install when install button clicked", async () => {
    const open_install = vi.fn()
    render(OAuthInstallStep, {
      props: {
        state: make_state(),
        open_install,
        verify_access: noop_async,
        reset: noop,
      },
    })
    screen.getByText("Install Kiln Sync on GitHub").closest("button")?.click()
    expect(open_install).toHaveBeenCalledOnce()
  })

  it("calls reset when start over clicked", async () => {
    const reset = vi.fn()
    render(OAuthInstallStep, {
      props: {
        state: make_state(),
        open_install: noop,
        verify_access: noop_async,
        reset,
      },
    })
    screen.getByText("Start over").click()
    expect(reset).toHaveBeenCalledOnce()
  })

  it("shows popup-blocked copy fallback when popup_blocked is true", () => {
    const { container } = render(OAuthInstallStep, {
      props: {
        state: make_state({
          popup_blocked: true,
          install_url: "https://github.com/apps/kiln/installations/new",
        }),
        open_install: noop,
        verify_access: noop_async,
        reset: noop,
      },
    })
    const input = container.querySelector("input[readonly]") as HTMLInputElement
    expect(input).not.toBeNull()
    expect(input.value).toBe("https://github.com/apps/kiln/installations/new")
    expect(screen.getByText("Copy")).not.toBeNull()
    expect(screen.getByText(/blocked the popup/)).not.toBeNull()
    expect(screen.queryByText("Install Kiln Sync on GitHub")).toBeNull()
  })
})
