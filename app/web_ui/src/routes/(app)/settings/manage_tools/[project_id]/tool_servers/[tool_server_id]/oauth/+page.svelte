<script lang="ts">
  import { onMount } from "svelte"
  import { page } from "$app/stores"
  import { base_url } from "$lib/api_client"

  $: project_id = $page.params.project_id
  $: tool_server_id = $page.params.tool_server_id
  $: code = $page.url.searchParams.get("code")
  $: state = $page.url.searchParams.get("state")
  $: error_param = $page.url.searchParams.get("error")
  $: error_description = $page.url.searchParams.get("error_description")

  let status: "loading" | "success" | "error" = "loading"
  let error_message: string | null = null

  $: detail_link = `/settings/manage_tools/${project_id}/tool_servers/${tool_server_id}`

  onMount(async () => {
    if (error_param) {
      status = "error"
      error_message = error_description || error_param
      return
    }

    if (!code || !state) {
      status = "error"
      error_message = "Missing OAuth parameters in the callback URL."
      return
    }

    const response = await fetch(
      `${base_url}/api/projects/${project_id}/tool_servers/${tool_server_id}/add_oauth`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          code,
          state,
          error: error_param,
          error_description,
        }),
      },
    )

    if (!response.ok) {
      status = "error"
      try {
        const result = (await response.json()) as { detail?: string }
        error_message =
          result?.detail ||
          response.statusText ||
          "Failed to save OAuth credentials."
      } catch (err) {
        const message =
          err instanceof Error
            ? err.message
            : "Failed to save OAuth credentials."
        error_message = message
      }
      return
    }

    status = "success"
  })
</script>

<div
  class="min-h-[60vh] flex flex-col items-center justify-center gap-6 px-4 text-center"
>
  {#if status === "loading"}
    <div class="flex flex-col items-center gap-2">
      <div class="loading loading-spinner loading-lg"></div>
      <div class="text-sm text-gray-500">Completing OAuth connection…</div>
    </div>
  {:else if status === "success"}
    <div class="flex flex-col items-center gap-4">
      <div class="text-2xl font-semibold">OAuth Connection Successful</div>
      <div class="text-sm text-gray-500 max-w-xl">
        Your remote MCP server is now connected.
      </div>
      <a class="btn btn-primary" href={detail_link}>Back to Tool Server</a>
    </div>
  {:else}
    <div class="flex flex-col items-center gap-4">
      <div class="text-2xl font-semibold text-error">
        OAuth Connection Failed
      </div>
      <div class="text-sm text-error max-w-xl">
        {error_message || "An unknown error occurred while completing OAuth."}
      </div>
      <a class="btn btn-primary" href={detail_link}>Return to Tool Server</a>
    </div>
  {/if}
</div>
