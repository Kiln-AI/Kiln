<script lang="ts">
  import { onMount } from "svelte"
  import createKindeClient from "@kinde-oss/kinde-auth-pkce-js"
  import { base_url } from "$lib/api_client"
  import posthog from "posthog-js"

  export let onSuccess: () => void
  export let onCancel: () => void

  let kindeClient: Awaited<ReturnType<typeof createKindeClient>> | null = null
  let apiKey = ""
  let apiKeyError = false
  let apiKeyMessage: string | null = null
  let submitting = false

  const KILN_ACCOUNT_DOMAIN = "https://account.kiln.tech"
  const KILN_ACCOUNT_CLIENT_ID = "2428f47a1e0b404b82e68400a2d580c6"

  async function initKindeClient() {
    if (kindeClient) return kindeClient

    kindeClient = await createKindeClient({
      client_id: KILN_ACCOUNT_CLIENT_ID,
      domain: KILN_ACCOUNT_DOMAIN,
      redirect_uri: window.location.origin + window.location.pathname,
      on_redirect_callback: () => {},
    })

    return kindeClient
  }

  async function openSignup() {
    try {
      const kinde = await initKindeClient()
      if (!kinde) {
        apiKeyError = true
        apiKeyMessage = "Kinde configuration is missing"
        return
      }

      await kinde.register()
    } catch (e) {
      console.error("openSignup error", e)
      apiKeyError = true
      apiKeyMessage = "Failed to open Kiln Copilot signup"
    }
  }

  async function openSelfServePortal() {
    try {
      const kinde = await initKindeClient()
      if (!kinde) {
        apiKeyError = true
        apiKeyMessage = "Please sign up first"
        return
      }

      const accessToken = await kinde.getToken()
      if (!accessToken) {
        apiKeyError = true
        apiKeyMessage = "Please sign up first before accessing the portal"
        return
      }

      const response = await fetch(
        `${KILN_ACCOUNT_DOMAIN}/account_api/v1/portal_link`,
        {
          headers: {
            Authorization: `Bearer ${accessToken}`,
            sub_nav: "api_keys",
          },
        },
      )

      if (!response.ok) {
        throw new Error("Failed to generate portal link")
      }

      const data = await response.json()
      window.open(data.url, "_blank")
    } catch (e) {
      console.error("openSelfServePortal error", e)
      apiKeyError = true
      apiKeyMessage =
        "Failed to open self-serve portal. Please try signing up first."
    }
  }

  async function submitApiKey() {
    if (!apiKey.trim()) {
      apiKeyError = true
      return
    }

    apiKeyError = false
    apiKeyMessage = null
    submitting = true

    try {
      const res = await fetch(base_url + "/api/provider/connect_api_key", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          provider: "kiln_copilot",
          key_data: {
            "API Key": apiKey,
          },
        }),
      })

      const data = await res.json()

      if (!res.ok) {
        apiKeyMessage =
          data.message || data.detail || "Failed to connect to provider"
        apiKeyError = true
        return
      }

      posthog.capture("connect_provider", {
        provider_id: "kiln_copilot",
      })

      onSuccess()
    } catch (e) {
      console.error("submitApiKey error", e)
      apiKeyMessage = "Failed to connect to provider (Exception: " + e + ")"
      apiKeyError = true
    } finally {
      submitting = false
    }
  }

  onMount(async () => {
    if (
      window.location.search.includes("code=") ||
      window.location.search.includes("state=")
    ) {
      await initKindeClient()
    }
  })
</script>

<div class="grow h-full max-w-[400px] flex flex-col place-content-center">
  <div class="grow"></div>

  <h1 class="text-xl font-medium flex-none text-center">
    Connect Kiln Copilot
  </h1>

  <ol class="flex-none my-2 text-gray-700">
    <li class="list-decimal pl-1 mx-8 my-4">
      <button class="link" on:click={openSignup}>Sign Up</button>
      to create your Kiln Copilot account.
    </li>
    <li class="list-decimal pl-1 mx-8 my-4">
      After registration,
      <button class="link" on:click={openSelfServePortal}>
        open the self-serve portal.
      </button>
      Go to 'API keys' section and create an API key.
    </li>
    <li class="list-decimal pl-1 mx-8 my-4">
      Copy your API key, paste it below and click 'Connect'.
    </li>
  </ol>

  {#if apiKeyMessage}
    <p class="text-error text-center pb-4">{apiKeyMessage}</p>
  {/if}

  <div class="flex flex-row gap-4 items-center">
    <div class="grow flex flex-col gap-2">
      <input
        type="text"
        id="API Key"
        placeholder="API Key"
        class="input input-bordered w-full max-w-[300px] {apiKeyError
          ? 'input-error'
          : ''}"
        bind:value={apiKey}
        on:input={() => (apiKeyError = false)}
      />
    </div>
    <button
      class="btn min-w-[130px]"
      on:click={submitApiKey}
      disabled={submitting}
    >
      {#if submitting}
        <div class="loading loading-spinner loading-md"></div>
      {:else}
        Connect
      {/if}
    </button>
  </div>

  <button class="link text-center text-sm mt-8" on:click={onCancel}>
    Cancel setting up Kiln Copilot
  </button>

  <div class="grow-[1.5]"></div>
</div>
