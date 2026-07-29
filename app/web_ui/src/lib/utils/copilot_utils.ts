import { client } from "$lib/api_client"

/**
 * Check if Kiln Copilot is connected (has API key configured)
 * @returns true if copilot is available, false otherwise
 * @throws Error if the settings API call fails
 */
export async function checkKilnCopilotAvailable(): Promise<boolean> {
  // Bounded: callers gate UI (e.g. the Kiln Pro button's spinner) on this
  // call, so a hung request must fail rather than stick forever.
  const { data, error } = await client.GET("/api/settings", {
    signal: AbortSignal.timeout(10_000),
  })
  if (error) {
    throw error
  }
  if (!data) {
    throw new Error("Failed to load Kiln settings")
  }
  return !!data["kiln_copilot_api_key"]
}
