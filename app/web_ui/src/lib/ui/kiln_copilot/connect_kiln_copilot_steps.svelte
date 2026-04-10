<script lang="ts">
  import { onMount } from "svelte"
  import createKindeClient from "@kinde-oss/kinde-auth-pkce-js"
  import { base_url } from "$lib/api_client"
  import posthog from "posthog-js"
  import { env } from "$env/dynamic/public"

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

    onSuccess()
  }

  onMount(async () => {
    const params = new URLSearchParams(window.location.search)
    if (params.has("code")) {
      await createApiKeyFromToken()
    }
  })
</script>

<h1 class="text-xl font-medium flex-none text-center">Connect Kiln Copilot</h1>

{#if showCheckmark}
  <div class="flex justify-center py-4">
    <img src="/images/circle-check.svg" class="size-8" alt="Connected" />
  </div>
{:else if errorMessage}
  <p class="text-error text-center pt-4 pb-2">{errorMessage}</p>
  <div class="flex justify-center pb-4">
    <button
      class="btn min-w-[130px]"
      on:click={tokenExchangeFailed ? createApiKeyFromToken : openSignup}
      >Try Again</button
    >
  </div>
{:else}
  <p class="text-center text-gray-700 mx-8 my-4">
    Sign in or create an account to get started.
  </p>
  <div class="flex justify-center pt-2">
    <button
      class="btn min-w-[130px]"
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
