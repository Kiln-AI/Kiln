// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from "vitest"
import { render, cleanup, fireEvent, waitFor } from "@testing-library/svelte"
import { tick } from "svelte"

vi.mock("$lib/git_sync/api", () => ({
  listBranches: vi.fn(),
  cloneRepo: vi.fn(),
  testWriteAccess: vi.fn(),
}))

import StepBranch from "./step_branch.svelte"
import { cloneRepo, testWriteAccess } from "$lib/git_sync/api"

const baseProps = {
  git_url: "https://github.com/org/repo.git",
  pat_token: "token",
  oauth_token: null,
  auth_mode: "pat_token",
  on_selected: vi.fn(),
}

beforeEach(() => {
  vi.mocked(cloneRepo).mockResolvedValue({
    clone_path: "/tmp/clone_abc",
    success: true,
    message: "OK",
  })
  vi.mocked(testWriteAccess).mockResolvedValue({
    success: true,
    message: "Write access confirmed",
    auth_required: false,
    write_denied: false,
    auth_method: "pat_token",
  })
  vi.mocked(baseProps.on_selected).mockReset()
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

// Svelte 4 async onMount callbacks do not execute in jsdom/vitest, so we
// call the component's exported functions directly to exercise the
// write-denied detection, auth-required redirect, and success paths.

describe("StepBranch", () => {
  it("renders loading spinner as initial state", () => {
    const { container } = render(StepBranch, { props: baseProps })
    expect(container.textContent).toContain("Select Branch")
    expect(container.querySelector(".loading-spinner")).not.toBeNull()
  })

  it("shows write denied state when write access is rejected", async () => {
    vi.mocked(testWriteAccess).mockResolvedValue({
      success: false,
      message: "Push rejected for refs/heads/main: permission denied",
      auth_required: false,
      write_denied: true,
      auth_method: null,
    })

    const { container, component } = render(StepBranch, { props: baseProps })

    await component.clone_and_test()
    await tick()

    expect(container.textContent).toContain("Write Access Required")
    expect(container.textContent).toContain("read/write access")
    expect(container.textContent).toContain("read-only")
    expect(container.textContent).toContain("Choose Another Branch")
    expect(container.textContent).not.toContain("Select Branch")
    expect(container.querySelector(".rounded-full")).not.toBeNull()
    expect(baseProps.on_selected).not.toHaveBeenCalled()
  })

  it("choose another branch clears write denied state", async () => {
    vi.mocked(testWriteAccess).mockResolvedValue({
      success: false,
      message: "Push rejected for refs/heads/main: permission denied",
      auth_required: false,
      write_denied: true,
      auth_method: null,
    })

    const { container, component, getByText } = render(StepBranch, {
      props: baseProps,
    })

    await component.clone_and_test()
    await tick()

    expect(container.textContent).toContain("Write Access Required")

    const chooseBtn = getByText("Choose Another Branch")
    await fireEvent.click(chooseBtn)
    await tick()

    expect(container.textContent).not.toContain("Write Access Required")
    expect(container.textContent).toContain("Select Branch")
  })

  it("choose_another_branch exported function clears state", async () => {
    vi.mocked(testWriteAccess).mockResolvedValue({
      success: false,
      message: "denied",
      auth_required: false,
      write_denied: true,
      auth_method: null,
    })

    const { container, component } = render(StepBranch, { props: baseProps })

    await component.clone_and_test()
    await tick()

    expect(container.textContent).toContain("Write Access Required")

    component.choose_another_branch()
    await tick()

    expect(container.textContent).not.toContain("Write Access Required")
  })

  it("redirects to credentials on auth_required", async () => {
    vi.mocked(testWriteAccess).mockResolvedValue({
      success: false,
      message: "Authentication failed - check your token permissions",
      auth_required: true,
      write_denied: false,
      auth_method: null,
    })

    const { component } = render(StepBranch, { props: baseProps })

    await component.clone_and_test()
    await tick()

    expect(baseProps.on_selected).toHaveBeenCalledWith(
      "",
      "/tmp/clone_abc",
      true,
    )
  })

  it("proceeds on successful write access", async () => {
    const { component } = render(StepBranch, { props: baseProps })

    await component.clone_and_test()
    await tick()

    expect(baseProps.on_selected).toHaveBeenCalledWith(
      "",
      "/tmp/clone_abc",
      false,
    )
  })

  it("write_denied takes priority over auth_required", async () => {
    vi.mocked(testWriteAccess).mockResolvedValue({
      success: false,
      message: "denied",
      auth_required: true,
      write_denied: true,
      auth_method: null,
    })

    const { container, component } = render(StepBranch, { props: baseProps })

    await component.clone_and_test()
    await tick()

    expect(container.textContent).toContain("Write Access Required")
    expect(baseProps.on_selected).not.toHaveBeenCalled()
  })

  it("shows generic error for non-write-denied, non-auth failures", async () => {
    vi.mocked(testWriteAccess).mockResolvedValue({
      success: false,
      message: "Write access check failed: network timeout",
      auth_required: false,
      write_denied: false,
      auth_method: null,
    })

    const { container, component } = render(StepBranch, { props: baseProps })

    await component.clone_and_test()
    await tick()

    expect(container.textContent).not.toContain("Write Access Required")
    expect(baseProps.on_selected).not.toHaveBeenCalled()
  })
})
