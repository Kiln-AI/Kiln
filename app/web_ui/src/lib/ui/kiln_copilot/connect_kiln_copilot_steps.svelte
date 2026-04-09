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
      window.history.replaceState({}, "", window.location.pathname)

      posthog.capture("connect_provider", {
        provider_id: "kiln_copilot",
      })

      onSuccess()
    } catch (e) {
      console.error("createApiKeyFromToken error", e)
      errorMessage = "Failed to connect to Kiln Copilot. Please try again."
    } finally {
      connecting = false
    }
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
{:else}
  <ol class="flex-none my-2 text-gray-700">
    <li class="list-decimal pl-1 mx-8 my-4">
      <button class="link underline" on:click={openSignup}>Sign Up</button>
      to create your free Kiln Copilot account.
    </li>
    <li class="list-decimal pl-1 mx-8 my-4">
      {#if connecting}
        <span class="flex items-center gap-2">
          <span class="loading loading-spinner loading-sm"></span>
          Creating your API key...
        </span>
      {:else}
        Your API key will be created automatically.
      {/if}
    </li>
  </ol>
  {#if errorMessage}
    <p class="text-error text-center pb-2">{errorMessage}</p>
    <div class="flex justify-center pb-4">
      <button
        class="btn min-w-[130px]"
        on:click={tokenExchangeFailed ? createApiKeyFromToken : openSignup}
        >Try Again</button
      >
    </div>
  {/if}
{/if}
