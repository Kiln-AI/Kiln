// @vitest-environment jsdom
import {
  describe,
  it,
  expect,
  vi,
  afterEach,
  beforeAll,
  beforeEach,
} from "vitest"
import { render, cleanup, waitFor, fireEvent } from "@testing-library/svelte"
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

// jsdom has no HTMLDialogElement.showModal, which the reset arguments dialog
// opens with. This one only marks the dialog open.
beforeAll(() => {
  if (!HTMLDialogElement.prototype.showModal) {
    HTMLDialogElement.prototype.showModal = function () {
      this.open = true
    }
  }
})

beforeEach(() => {
  load_openenv_server.mockReset()
})
afterEach(() => cleanup())

function render_episode(episode: OpenEnvEpisode = EPISODE) {
  return render(OpenEnvEpisodeProperties, {
    props: { project_id: "p1", episode },
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
    expect(getByText("OpenEnv Server")).toBeTruthy()
    expect(getByText("Version")).toBeTruthy()
    expect(getByText("acme@1.0.0")).toBeTruthy()
  })

  it("names the saved preset whose arguments match, and the name opens them", async () => {
    load_openenv_server.mockResolvedValue({
      id: "openenv_1",
      name: "Acme",
      is_archived: false,
      named_reset_kwargs: [
        { name: "Other", reset_kwargs: { company: "acme" } },
        // Key order differs from the run's, and still matches.
        { name: "Agency", reset_kwargs: { role: "tech", company: "acme" } },
      ],
    })
    const { getByText, getByRole, queryByText } = render_episode()
    const preset = await waitFor(() => getByRole("button", { name: "Agency" }))
    expect(getByText("Environment Preset")).toBeTruthy()
    expect(queryByText("Environment Options")).toBeNull()

    await fireEvent.click(preset)
    expect(getByText("Agency", { selector: "h3" })).toBeTruthy()
    expect(document.body.textContent).toContain('"company": "acme"')
  })

  it("counts the arguments under Environment Options when no saved preset matches, and the count opens them", async () => {
    load_openenv_server.mockResolvedValue({
      id: "openenv_1",
      name: "Acme",
      is_archived: false,
      named_reset_kwargs: [{ name: "Agency", reset_kwargs: { company: "x" } }],
    })
    const { getByText, getByRole, queryByText } = render_episode()
    await waitFor(() => expect(load_openenv_server).toHaveBeenCalled())
    expect(getByText("Environment Options")).toBeTruthy()
    expect(queryByText("Environment Preset")).toBeNull()
    // The JSON isn't on the page until the count is clicked.
    expect(document.body.textContent).not.toContain('"company"')

    await fireEvent.click(getByRole("button", { name: "2 options" }))
    expect(getByText("Environment Options", { selector: "h3" })).toBeTruthy()
    expect(document.body.textContent).toContain('"company": "acme"')
    expect(document.body.textContent).toContain('"role": "tech"')
  })

  it("says 1 option for a single unmatched argument", () => {
    load_openenv_server.mockRejectedValue(new Error("OpenEnv not found"))
    const { getByRole } = render_episode({
      ...EPISODE,
      reset: { ...EPISODE.reset, reset_kwargs: { fixture: "agency" } },
    })
    expect(getByRole("button", { name: "1 option" })).toBeTruthy()
  })

  it("says None, with nothing to open, when the session reset with no arguments", () => {
    load_openenv_server.mockRejectedValue(new Error("OpenEnv not found"))
    const { getByText, queryAllByRole } = render_episode({
      ...EPISODE,
      reset: { ...EPISODE.reset, reset_kwargs: {} },
    })
    expect(getByText("None")).toBeTruthy()
    expect(
      queryAllByRole("button").filter((b) =>
        /option/.test(b.textContent ?? ""),
      ),
    ).toHaveLength(0)
  })

  it("falls back to the id when the OpenEnv server can't be loaded", async () => {
    load_openenv_server.mockRejectedValue(new Error("OpenEnv not found"))
    const { container } = render_episode()
    await waitFor(() => expect(load_openenv_server).toHaveBeenCalled())
    expect(container.querySelector("a")?.textContent).toBe("openenv_1")
  })
})
