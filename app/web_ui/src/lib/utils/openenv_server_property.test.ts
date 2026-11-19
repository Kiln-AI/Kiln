import { describe, it, expect, vi, beforeEach } from "vitest"
import { get } from "svelte/store"
import type { OpenEnvServer } from "$lib/types"

const { mock_load_openenv_server } = vi.hoisted(() => ({
  mock_load_openenv_server: vi.fn(),
}))

vi.mock("$lib/api/openenv_server_api", () => ({
  load_openenv_server: mock_load_openenv_server,
}))

import {
  create_openenv_server_loader,
  openenv_server_property,
} from "./openenv_server_property"

const SERVER: OpenEnvServer = {
  id: "openenv_1",
  name: "Shop Sim",
  is_archived: false,
  named_reset_kwargs: [],
}

const DETAIL_LINK = "/tools/proj1/openenv_servers/openenv_1"

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((r) => (resolve = r))
  return { promise, resolve }
}

describe("openenv_server_property", () => {
  it("shows the server's name, linked to its detail page", () => {
    expect(openenv_server_property("proj1", "openenv_1", SERVER)).toEqual({
      name: "OpenEnv Server",
      value: "Shop Sim",
      link: DETAIL_LINK,
    })
  })

  it("marks an archived server", () => {
    const archived = { ...SERVER, is_archived: true }
    expect(openenv_server_property("proj1", "openenv_1", archived).value).toBe(
      "Shop Sim (Archived)",
    )
  })

  it("shows the id of a server that couldn't be loaded, still linked", () => {
    const property = openenv_server_property("proj1", "openenv_1", null)
    expect(property.value).toBe("openenv_1")
    expect(property.link).toBe(DETAIL_LINK)
  })

  it("says it's loading before the server arrives", () => {
    expect(openenv_server_property("proj1", "openenv_1", undefined).value).toBe(
      "Loading...",
    )
  })
})

describe("create_openenv_server_loader", () => {
  beforeEach(() => {
    mock_load_openenv_server.mockReset()
  })

  it("holds the loaded server", async () => {
    mock_load_openenv_server.mockResolvedValue(SERVER)
    const loader = create_openenv_server_loader()

    await loader.load("proj1", "openenv_1")

    expect(mock_load_openenv_server).toHaveBeenCalledWith("proj1", "openenv_1")
    expect(get(loader)).toEqual(SERVER)
  })

  it("holds null when the server can't be loaded", async () => {
    mock_load_openenv_server.mockRejectedValue(new Error("Not found"))
    const loader = create_openenv_server_loader()

    await loader.load("proj1", "gone")

    expect(get(loader)).toBeNull()
  })

  it.each([null, undefined, ""])(
    "makes no request without a server id (%s)",
    async (openenv_server_id) => {
      const loader = create_openenv_server_loader()

      await loader.load("proj1", openenv_server_id)

      expect(mock_load_openenv_server).not.toHaveBeenCalled()
      expect(get(loader)).toBeUndefined()
    },
  )

  it("doesn't refetch the server it already holds", async () => {
    mock_load_openenv_server.mockResolvedValue(SERVER)
    const loader = create_openenv_server_loader()

    await loader.load("proj1", "openenv_1")
    await loader.load("proj1", "openenv_1")

    expect(mock_load_openenv_server).toHaveBeenCalledTimes(1)
    expect(get(loader)).toEqual(SERVER)
  })

  it("drops a reply to a load a later one replaced", async () => {
    const first = deferred<OpenEnvServer>()
    const second = deferred<OpenEnvServer>()
    mock_load_openenv_server
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise)
    const loader = create_openenv_server_loader()
    const other = { ...SERVER, id: "openenv_2", name: "Other" }

    const first_load = loader.load("proj1", "openenv_1")
    const second_load = loader.load("proj1", "openenv_2")
    second.resolve(other)
    await second_load
    first.resolve(SERVER)
    await first_load

    expect(get(loader)).toEqual(other)
  })

  it("clears the server when the eval has none", async () => {
    mock_load_openenv_server.mockResolvedValue(SERVER)
    const loader = create_openenv_server_loader()

    await loader.load("proj1", "openenv_1")
    await loader.load("proj1", null)

    expect(get(loader)).toBeUndefined()
  })
})
