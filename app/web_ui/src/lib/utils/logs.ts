import { client } from "$lib/api_client"

/**
 * Opens the application logs folder in the system file browser
 */
export async function view_logs(): Promise<void> {
  try {
    const { error } = await client.POST("/api/open_logs", {})
    if (error) {
      const errorMessage = (error as Record<string, unknown>)?.message
      if (typeof errorMessage === "string") {
        throw new Error(errorMessage)
      } else {
        throw new Error("Unknown error")
      }
    }
  } catch (e) {
    alert("Failed to open logs: " + e)
  }
}
