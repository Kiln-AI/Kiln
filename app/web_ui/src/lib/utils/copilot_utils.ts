import { client } from "$lib/api_client"

/**
 * Check if Kiln Copilot is connected with a valid API key.
 *
 * Hits the studio_server `/api/provider/verify_kiln_copilot_api_key`
 * endpoint, which (a) reads the stored copilot API key from local config,
 * (b) calls the Kiln server's `/v1/verify_api_key` to confirm the key still
 * works, and (c) clears the local key if the server explicitly rejects it
 * with 401/403 — so a stale key doesn't silently bypass the connect screen.
 *
 * @returns true if a stored key is present AND the Kiln server accepts it.
 * @throws Error if the studio_server call itself fails.
 */
export async function checkKilnCopilotAvailable(): Promise<boolean> {
  const { data, error } = await client.GET(
    "/api/provider/verify_kiln_copilot_api_key",
  )
  if (error) {
    throw error
  }
  if (!data) {
    throw new Error("Failed to verify Kiln Copilot API key")
  }
  return !!(data as { is_valid?: boolean }).is_valid
}
