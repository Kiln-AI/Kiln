import { writable, type Readable } from "svelte/store"
import type { OpenEnvServer } from "$lib/types"
import type { UiProperty } from "$lib/ui/property_list"
import { load_openenv_server } from "$lib/api/openenv_server_api"
import { openenv_server_detail_link } from "$lib/utils/openenv"

/**
 * An OpenEnv server being loaded for display: `undefined` while loading or with
 * nothing to load, `null` when it couldn't be loaded (usually deleted).
 */
export type LoadedOpenEnvServer = OpenEnvServer | null | undefined

/** The "OpenEnv Server" row a grounded eval shows on the spec and eval pages. */
export function openenv_server_property(
  project_id: string,
  openenv_server_id: string,
  openenv_server: LoadedOpenEnvServer,
): UiProperty {
  return {
    name: "OpenEnv Server",
    value: openenv_server_display_name(openenv_server_id, openenv_server),
    link: openenv_server_detail_link(project_id, openenv_server_id),
  }
}

function openenv_server_display_name(
  openenv_server_id: string,
  openenv_server: LoadedOpenEnvServer,
): string {
  if (openenv_server === undefined) {
    return "Loading..."
  }
  // A deleted server still has its id on the eval, which is shown instead.
  if (openenv_server === null) {
    return openenv_server_id
  }
  return openenv_server.is_archived
    ? `${openenv_server.name} (Archived)`
    : openenv_server.name
}

export type OpenEnvServerLoader = Readable<LoadedOpenEnvServer> & {
  load: (
    project_id: string,
    openenv_server_id: string | null | undefined,
  ) => Promise<void>
}

/**
 * Holds one OpenEnv server for a page. Each `load` of a different server
 * replaces the last, and a reply to a superseded load is dropped, so a slow
 * request can't show another eval's server. Loading the same server again is a
 * no-op: pages call `load` reactively, and an edit that replaces the eval object
 * shouldn't refetch or flash "Loading...".
 */
export function create_openenv_server_loader(): OpenEnvServerLoader {
  const { subscribe, set } = writable<LoadedOpenEnvServer>(undefined)
  let latest_load = 0
  let latest_key: string | null = null

  async function load(
    project_id: string,
    openenv_server_id: string | null | undefined,
  ): Promise<void> {
    const key = openenv_server_id ? `${project_id}/${openenv_server_id}` : ""
    if (key === latest_key) {
      return
    }
    latest_key = key
    const this_load = ++latest_load
    set(undefined)
    if (!openenv_server_id) {
      return
    }
    let openenv_server: OpenEnvServer | null
    try {
      openenv_server = await load_openenv_server(project_id, openenv_server_id)
    } catch {
      openenv_server = null
    }
    if (this_load === latest_load) {
      set(openenv_server)
    }
  }

  return { subscribe, load }
}
