import { client } from "$lib/api_client"

/**
 * Check if the user has specific entitlements (feature access)
 * @param featureCodes - Array of feature codes to check (e.g., ['prompt-optimization'])
 * @returns Record mapping each feature code to a boolean indicating if user has that entitlement
 * @throws Error if the entitlements API call fails
 */
export async function checkEntitlements(
  featureCodes: string[],
): Promise<Record<string, boolean>> {
  const { data, error } = await client.GET("/api/check_entitlements", {
    params: {
      query: {
        feature_codes: featureCodes.join(","),
      },
    },
  })
  if (error) {
    throw error
  }
  if (!data) {
    throw new Error("Failed to check entitlements")
  }
  return data
}
