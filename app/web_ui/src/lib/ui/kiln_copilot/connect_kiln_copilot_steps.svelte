<script lang="ts">
  import { onMount } from "svelte"
  import createKindeClient from "@kinde-oss/kinde-auth-pkce-js"
  import { base_url } from "$lib/api_client"
  import posthog from "posthog-js"
  import { env } from "$env/dynamic/public"
  import { setCopilotConnected } from "$lib/stores/copilot_connection_store"
  import CheckmarkIcon from "$lib/ui/icons/checkmark_icon.svelte"

  export let onSuccess: () => void
  export let showCheckmark = false

  let kindeClient: Awaited<ReturnType<typeof createKindeClient>> | null = null
  let connecting = false
  let errorMessage: string | null = null
  let tokenExchangeFailed = false

  const KINDE_ACCOUNT_DOMAIN =
    env.PUBLIC_KINDE_ACCOUNT_DOMAIN || "https://account.kiln.tech"
  const KINDE_ACCOUNT_CLIENT_ID =
    env.PUBLIC_KINDE_ACCOUNT_CLIENT_ID || "2428f47a1e0b404b82e68400a2d580c6"

  async function initKindeClient() {
    if (kindeClient) return kindeClient

    kindeClient = await createKindeClient({
      client_id: KINDE_ACCOUNT_CLIENT_ID,
      domain: KINDE_ACCOUNT_DOMAIN,
      redirect_uri: window.location.origin + window.location.pathname,
      // Kinde SDK requires this callback; we handle the redirect ourselves in onMount
      on_redirect_callback: () => {},
    })

    return kindeClient
  }

  async function openSignup() {
    try {
      const kinde = await initKindeClient()
      if (!kinde) {
        errorMessage = "Kinde configuration is missing"
        return
      }

      await kinde.register()
    } catch (e) {
      console.error("openSignup error", e)
      errorMessage = "Failed to open Kiln Copilot signup"
    }
  }

  async function createApiKeyFromToken() {
    connecting = true
    errorMessage = null
    tokenExchangeFailed = false

    try {
      const kinde = await initKindeClient()
      if (!kinde) {
        errorMessage = "Failed to initialize authentication"
        connecting = false
        return
      }

      const accessToken = await kinde.getToken()
      if (!accessToken) {
        errorMessage =
          "Failed to get access token. Please try signing in again."
        connecting = false
        return
      }

      tokenExchangeFailed = true

      const res = await fetch(
        base_url + "/api/provider/create_kiln_copilot_api_key",
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            access_token: accessToken,
          }),
        },
      )

      const data = await res.json()

      if (!res.ok) {
        errorMessage = data.message || data.detail || "Failed to create API key"
        connecting = false
        return
      }

      tokenExchangeFailed = false
    } catch (e) {
      console.error("createApiKeyFromToken error", e)
      errorMessage = "Failed to connect to Kiln Copilot. Please try again."
      return
    } finally {
      connecting = false
    }

    window.history.replaceState({}, "", window.location.pathname)

    posthog.capture("connect_provider", {
      provider_id: "kiln_copilot",
    })

    setCopilotConnected(true)
    onSuccess()
  }

  onMount(async () => {
    const params = new URLSearchParams(window.location.search)
    if (params.has("code")) {
      await createApiKeyFromToken()
    }
  })
</script>

{#if showCheckmark}
  <div class="h-12 w-12 mx-auto mb-2 text-success">
    <CheckmarkIcon />
  </div>
  <h1 class="text-xl font-medium flex-none text-center">Connected</h1>
{:else if errorMessage}
  <h1 class="text-xl font-medium flex-none text-center">Error Connecting</h1>
  <p class="text-error text-center mx-8 my-4 text-sm">{errorMessage}</p>
  <div class="flex justify-center">
    <button
      class="btn btn-primary btn-wide"
      on:click={tokenExchangeFailed ? createApiKeyFromToken : openSignup}
      >Try Again</button
    >
  </div>
{:else}
  <div class="h-12 w-12 mx-auto mb-4">
    <img src="/images/animated_logo.svg" alt="Kiln logo" />
  </div>
  <h1 class="text-xl font-medium flex-none text-center">
    Connect Kiln Copilot
  </h1>
  <p class="text-center font-light mx-8 mb-8">Sign in or create an account.</p>
  <div class="flex justify-center">
    <button
      class="btn btn-primary btn-wide"
      on:click={openSignup}
      disabled={connecting}
    >
      {#if connecting}
        <div class="loading loading-spinner loading-md"></div>
      {:else}
        Connect
      {/if}
    </button>
  </div>
{/if}
