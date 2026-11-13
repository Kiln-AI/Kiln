// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from "vitest"
import { render, cleanup, waitFor } from "@testing-library/svelte"
import type { OpenEnvServer, OpenEnvEpisode } from "$lib/types"

const load_openenv_server = vi.fn<[string, string], Promise<OpenEnvServer>>()
vi.mock("$lib/api/openenv_server_api", () => ({
  load_openenv_server: (...args: [string, string]) =>
    load_openenv_server(...args),
}))
vi.mock("$app/navigation", () => ({ goto: vi.fn() }))

const OpenEnvEpisodeProperties = (
  await import("./openenv_episode_properties.svelte")
).default

const EPISODE: OpenEnvEpisode = {
  reset: {
    openenv_server_id: "openenv_1",
    reset_kwargs: { company: "acme", role: "tech" },
  },
  episode_id: "ep_1",
  openenv_version: "acme@1.0.0",
}

beforeEach(() => {
  load_openenv_server.mockReset()
})
afterEach(() => cleanup())

function render_episode() {
  return render(OpenEnvEpisodeProperties, {
    props: { project_id: "p1", episode: EPISODE },
  })
}

describe("OpenEnvEpisodeProperties", () => {
  it("names the OpenEnv server, links its page, and shows the version and reset arguments", async () => {
    load_openenv_server.mockResolvedValue({
      id: "openenv_1",
      name: "Acme",
      is_archived: false,
    })
    const { container, getByText } = render_episode()
    expect(getByText("OpenEnv", { selector: "div.text-xl" })).toBeTruthy()

    await waitFor(() =>
      expect(container.querySelector("a")?.textContent).toBe("Acme"),
    )
    expect(load_openenv_server).toHaveBeenCalledWith("p1", "openenv_1")
    expect(container.querySelector("a")?.getAttribute("href")).toBe(
      "/tools/p1/openenv_servers/openenv_1",
    )
    expect(container.querySelector("pre")?.textContent).toBe(
      '{\n  "company": "acme",\n  "role": "tech"\n}',
    )
    expect(getByText("OpenEnv Server")).toBeTruthy()
    expect(getByText("Version")).toBeTruthy()
    expect(getByText("acme@1.0.0")).toBeTruthy()
  })

  it("falls back to the id when the OpenEnv server can't be loaded", async () => {
    load_openenv_server.mockRejectedValue(new Error("OpenEnv not found"))
    const { container } = render_episode()
    await waitFor(() => expect(load_openenv_server).toHaveBeenCalled())
    expect(container.querySelector("a")?.textContent).toBe("openenv_1")
  })
})
