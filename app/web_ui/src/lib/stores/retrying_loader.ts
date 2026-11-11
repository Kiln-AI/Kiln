// available_model_details() starts loads from reactive statements, and a
// failed load writes to the store those statements read. Without a delay
// between retries, a backend that is down gets a request loop.
export const LOAD_RETRY_DELAY_MS = 5000

export type RetryingLoaderHandlers<T> = {
  fetch: () => Promise<T>
  on_start?: () => void
  on_loaded: (data: T) => void
  on_error: (error: unknown) => void
}

/**
 * Loads data once and keeps it until `reset()`.
 *
 * - Concurrent `load()` calls share one request.
 * - After `fetch` fails, `load()` retries only once LOAD_RETRY_DELAY_MS has
 *   passed. Earlier calls resolve with no request.
 * - A result or error that arrives after `reset()` is dropped, and no handler
 *   runs for it.
 */
export function create_retrying_loader<T>(handlers: RetryingLoaderHandlers<T>) {
  let state: "not_loaded" | "loaded" | "error_loading" = "not_loaded"
  let in_flight: Promise<void> | null = null
  let last_error_at = 0
  let generation = 0

  async function run(load_generation: number) {
    handlers.on_start?.()
    try {
      const data = await handlers.fetch()
      if (load_generation !== generation) {
        return
      }
      handlers.on_loaded(data)
      state = "loaded"
    } catch (error: unknown) {
      if (load_generation !== generation) {
        return
      }
      handlers.on_error(error)
      state = "error_loading"
      last_error_at = Date.now()
    }
  }

  function load(): Promise<void> {
    if (in_flight) {
      return in_flight
    }
    if (state === "loaded") {
      return Promise.resolve()
    }
    if (
      state === "error_loading" &&
      Date.now() - last_error_at < LOAD_RETRY_DELAY_MS
    ) {
      return Promise.resolve()
    }
    const load_generation = generation
    in_flight = run(load_generation).finally(() => {
      if (load_generation === generation) {
        in_flight = null
      }
    })
    return in_flight
  }

  function reset() {
    generation++
    in_flight = null
    state = "not_loaded"
    last_error_at = 0
  }

  return { load, reset }
}
