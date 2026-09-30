import { writable } from "svelte/store"
import { client } from "$lib/api_client"

// Whether the desktop's assistant debug log (KILN_CHAT_DEBUG_LOG) is on. The
// chat footer shows the copy-conversation-id widget while it is.
export const chat_debug_log_enabled = writable(false)

export async function load_chat_debug_status(): Promise<void> {
  try {
    const { data } = await client.GET("/api/chat/debug_status")
    chat_debug_log_enabled.set(Boolean(data?.debug_log_enabled))
  } catch {
    // Debug affordance only: never surface an error for it.
  }
}
