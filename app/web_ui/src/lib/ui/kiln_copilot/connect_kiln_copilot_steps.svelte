<script lang="ts">
  import { onMount } from "svelte"
  import { base_url } from "$lib/api_client"
  import posthog from "posthog-js"
  import {
    initKindeClient,
    openSelfServePortal as openSelfServePortalUtil,
  } from "$lib/utils/copilot_utils"

  export let onSuccess: () => void
  export let showCheckmark = false

  let apiKey = ""
  let apiKeyError = false
  let apiKeyMessage: string | null = null
  let submitting = false

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
    const result = await openSelfServePortalUtil()
    if (!result.success) {
      apiKeyError = true
      apiKeyMessage = result.error || "Failed to open self-serve portal"
    }
  }

  export async function submitApiKey() {
    if (!apiKey.trim()) {
      apiKeyError = true
      return false
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
        return false
      }

      posthog.capture("connect_provider", {
        provider_id: "kiln_copilot",
      })

      onSuccess()
      return true
    } catch (e) {
      console.error("submitApiKey error", e)
      apiKeyMessage = "Failed to connect to provider (Exception: " + e + ")"
      apiKeyError = true
      return false
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

<h1 class="text-xl font-medium text-center mb-2">Connect Kiln Copilot</h1>

<ol class="mb-2 text-gray-700">
  <li class="list-decimal pl-1 mx-8 mb-4">
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
    {:else if showCheckmark}
      <img
        src="/images/circle-check.svg"
        class="size-6 group-hover:hidden"
        alt="Connected"
      />
    {:else}
      Connect
    {/if}
  </button>
</div>
