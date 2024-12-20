import { createKilnError, KilnError } from "$lib/utils/error_handlers"
import { writable } from "svelte/store"

export const app_version = "0.8.0"

export type UpdateCheckResult = {
  has_update: boolean
  latest_version: string
  link: string
}

export type UpdateState = {
  update_result: UpdateCheckResult | null
  update_loading: boolean
  update_error: KilnError | null
}

export const default_update_state: UpdateState = {
  update_result: null,
  update_loading: false,
  update_error: null,
}

export const update_info = writable<UpdateState>(default_update_state)

export async function update_update_store() {
  let update_result: UpdateCheckResult | null = null
  let update_error: KilnError | null = null
  try {
    update_info.update(() => default_update_state)
    const update = await check_for_update()
    if (update instanceof KilnError) {
      update_error = update
    } else {
      update_result = update
    }
  } catch (e) {
    update_error = createKilnError(e)
  } finally {
    update_info.update(() => ({
      update_loading: false,
      update_result,
      update_error,
    }))
  }
}

export async function check_for_update(): Promise<
  UpdateCheckResult | KilnError
> {
  try {
    const response = await fetch(
      "https://api.github.com/repos/Kiln-AI/Kiln/releases/latest",
    )
    const data = await response.json()
    const html_url = data.html_url
    const full_version = data.tag_name
    if (!html_url || !full_version) {
      return new KilnError("Failed to fetch update data", [])
    }
    const [version] = full_version.split("-")
    return {
      has_update: semantic_version_compare(version, app_version),
      latest_version: full_version,
      link: html_url,
    }
  } catch (e) {
    return createKilnError(e)
  }
}

export function semantic_version_compare(a: string, b: string): boolean {
  // Strip leading 'v' if present
  const clean_a = a.replace(/^v/, "")
  const clean_b = b.replace(/^v/, "")

  const a_parts = clean_a.split(".").map(Number)
  const b_parts = clean_b.split(".").map(Number)

  // Pad shorter array with zeros to match length
  const max_length = Math.max(a_parts.length, b_parts.length)
  while (a_parts.length < max_length) a_parts.push(0)
  while (b_parts.length < max_length) b_parts.push(0)

  // Compare each part from left to right
  for (let i = 0; i < max_length; i++) {
    if (a_parts[i] > b_parts[i]) return true
    if (a_parts[i] < b_parts[i]) return false
  }

  return false // versions are equal
}
