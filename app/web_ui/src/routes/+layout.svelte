<script lang="ts">
  import "../app.css"
  import { navigating } from "$app/stores"
  import { expoOut } from "svelte/easing"
  import { slide } from "svelte/transition"
  import { onMount } from "svelte"
  import { goto } from "$app/navigation"
  import {
    current_project,
    load_projects,
    projects,
    load_current_task,
    current_task,
  } from "$lib/stores"
  import { get } from "svelte/store"
  import { KilnError } from "$lib/utils/error_handlers"
  import { createKilnError } from "$lib/utils/error_handlers"
  import { page } from "$app/stores"
  let loading = true
  let load_error: string | null = null
  import posthog from "posthog-js"
  import { browser } from "$app/environment"
  import { beforeNavigate, afterNavigate } from "$app/navigation"

  function sanitize_route_id(route_id: string | null | undefined) {
    if (!route_id) {
      return "/unknown"
    }
    // Strip components in round brackets like "(app)" from the route
    let sanitized = route_id.replace(/\/?\([^)]*\)/g, "")
    // Strip square brackets like "[id]" from the route
    sanitized = sanitized.replace(/\[([^\]]*)\]/g, "$1")
    // URL encode characters that aren't valid in URLs, but preserve slashes
    sanitized = sanitized
      .split("/")
      .map((segment) => encodeURIComponent(segment))
      .join("/")
    // Ensure route always starts with a slash
    if (!sanitized.startsWith("/")) {
      sanitized = "/" + sanitized
    }
    return sanitized
  }

  function get_route_info() {
    const route_id = sanitize_route_id(get(page).route.id)
    const url = window.location.origin + route_id
    return { route_id, url }
  }

  if (browser) {
    beforeNavigate(() => {
      const { route_id, url } = get_route_info()
      posthog.capture("$pageleave", { $current_url: url, $pathname: route_id })
    })
    afterNavigate(() => {
      const { route_id, url } = get_route_info()
      posthog.capture("$pageview", { $current_url: url, $pathname: route_id })
    })
  }

  // Our (app) routes expect a current project and task.
  // This function checks if we have them, and redirects to the setup flow if not.
  const check_needs_setup = async () => {
    try {
      await load_projects()
      const all_projects = get(projects)
      if (all_projects?.error) {
        throw new KilnError(all_projects.error, null)
      }
      // No projects, go to setup to get started
      if (all_projects?.projects?.length == 0) {
        goto("/setup")
        return
      }
      // We have projects, but no current project. Select screen allows creating tasks, or selecting existing ones.
      if (!$current_project || !$current_project.id) {
        goto("/setup/select_task")
        return
      }
      // we have a current project, but no current task.
      // Go to setup to create one (or select one)
      await load_current_task($current_project?.id)
      if (!$current_task) {
        goto("/setup/select_task")
        return
      }
    } catch (e: unknown) {
      load_error = createKilnError(e).getMessage()
    } finally {
      loading = false
    }
  }

  onMount(() => {
    check_needs_setup()
  })
</script>

<svelte:head>
  <title>Kiln</title>
  <meta name="description" content="The easiest way to built AI products" />

  <link
    rel="apple-touch-icon"
    sizes="180x180"
    href="/favicons/apple-touch-icon.png"
  />
  <link
    rel="icon"
    type="image/png"
    sizes="32x32"
    href="/favicons/favicon-32x32.png"
  />
  <link
    rel="icon"
    type="image/png"
    sizes="16x16"
    href="/favicons/favicon-16x16.png"
  />
  <link rel="manifest" href="/favicons/site.webmanifest" />
</svelte:head>

{#if loading || load_error}
  <div
    class="fixed w-full top-0 right-0 left-0 bottom-0 bg-base-200 z-[1000] flex place-items-center place-content-center"
  >
    {#if load_error}
      <span class="text-center flex flex-col gap-4">
        <h1 class="text-2xl font-bold">Error loading projects</h1>
        <p class="text-error">{load_error}</p>
        <button
          class="btn btn-primary btn-sm"
          on:click={() => window.location.reload()}
        >
          Retry
        </button>
      </span>
    {:else}
      <span class="loading loading-spinner loading-lg"></span>
    {/if}
  </div>
{/if}

{#if $navigating}
  <!--
    Loading animation for next page since svelte doesn't show any indicator.
     - delay 100ms because most page loads are instant, and we don't want to flash
     - long 12s duration because we don't actually know how long it will take
     - exponential easing so fast loads (>100ms and <1s) still see enough progress,
       while slow networks see it moving for a full 12 seconds
  -->
  <div
    class="fixed w-full top-0 right-0 left-0 h-1 z-50 bg-primary"
    in:slide={{ delay: 100, duration: 12000, axis: "x", easing: expoOut }}
  ></div>
{/if}
<slot />
