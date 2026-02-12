import { client } from "$lib/api_client"
import createKindeClient from "@kinde-oss/kinde-auth-pkce-js"
import { env } from "$env/dynamic/public"

export const KINDE_ACCOUNT_DOMAIN =
  env.PUBLIC_KINDE_ACCOUNT_DOMAIN || "https://account.kiln.tech"
export const KINDE_ACCOUNT_CLIENT_ID =
  env.PUBLIC_KINDE_ACCOUNT_CLIENT_ID || "2428f47a1e0b404b82e68400a2d580c6"

let kindeClientInstance: Awaited<ReturnType<typeof createKindeClient>> | null =
  null

/**
 * Initialize or return the existing Kinde client
 */
export async function initKindeClient() {
  if (kindeClientInstance) return kindeClientInstance

  kindeClientInstance = await createKindeClient({
    client_id: KINDE_ACCOUNT_CLIENT_ID,
    domain: KINDE_ACCOUNT_DOMAIN,
    redirect_uri: window.location.origin + window.location.pathname,
    on_redirect_callback: () => {},
  })

  return kindeClientInstance
}

/**
 * Open the Kinde self-serve portal in a new tab
 * @returns An object with success status and optional error message
 */
export async function openSelfServePortal(): Promise<{
  success: boolean
  error?: string
}> {
  try {
    const kinde = await initKindeClient()
    if (!kinde) {
      return { success: false, error: "Please sign up first" }
    }

    const accessToken = await kinde.getToken()
    if (!accessToken) {
      return {
        success: false,
        error: "Please sign up first before accessing the portal",
      }
    }

    const response = await fetch(
      `${KINDE_ACCOUNT_DOMAIN}/account_api/v1/portal_link`,
      {
        headers: {
          Authorization: `Bearer ${accessToken}`,
        },
      },
    )

    if (!response.ok) {
      throw new Error("Failed to generate portal link")
    }

    const data = await response.json()
    window.open(data.url, "_blank")
    return { success: true }
  } catch (e) {
    console.error("openSelfServePortal error", e)
    return {
      success: false,
      error: "Failed to open self-serve portal. Please try signing up first.",
    }
  }
}

/**
 * Check if Kiln Copilot is connected (has API key configured)
 * @returns true if copilot is available, false otherwise
 * @throws Error if the settings API call fails
 */
export async function checkKilnCopilotAvailable(): Promise<boolean> {
  const { data, error } = await client.GET("/api/settings")
  if (error) {
    throw error
  }
  if (!data) {
    throw new Error("Failed to load Kiln settings")
  }
  return !!data["kiln_copilot_api_key"]
}
