<script lang="ts">
  import posthog from "posthog-js"
  import { chat_cost_disclaimer_acknowledged } from "$lib/stores"
  import Dialog from "$lib/ui/dialog.svelte"

  let dialog: Dialog

  let pendingResolve: ((approved: boolean) => void) | null = null
  let pendingPromise: Promise<boolean> | null = null

  export function prompt(): Promise<boolean> {
    if (pendingPromise) return pendingPromise
    posthog.capture("chat_cost_disclaimer_shown")
    pendingPromise = new Promise<boolean>((resolve) => {
      pendingResolve = resolve
      dialog.show()
    })
    return pendingPromise
  }

  function approve(): boolean {
    posthog.capture("chat_cost_disclaimer_accepted")
    chat_cost_disclaimer_acknowledged.set(true)
    const resolve = pendingResolve
    pendingResolve = null
    pendingPromise = null
    resolve?.(true)
    return true // close dialog
  }

  function dismiss() {
    if (pendingResolve === null) return
    posthog.capture("chat_cost_disclaimer_declined")
    const resolve = pendingResolve
    pendingResolve = null
    pendingPromise = null
    resolve?.(false)
  }

  const items: { icon: string; title: string; description: string }[] = [
    {
      icon: "M7.5 8.25h9m-9 3H12m-9.75 1.51c0 1.6 1.123 2.994 2.707 3.227 1.129.166 2.27.293 3.423.379.35.026.67.21.865.501L12 21l2.755-4.133a1.14 1.14 0 0 1 .865-.501 48.172 48.172 0 0 0 3.423-.379c1.584-.233 2.707-1.626 2.707-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0 0 12 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018Z",
      title: "Your data is sent to Kiln's servers",
      description:
        "Project metadata, tasks, runs, eval results and other project data are sent to fulfill your requests.",
    },
    {
      icon: "m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L10.582 16.07a4.5 4.5 0 0 1-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 0 1 1.13-1.897l8.932-8.931Zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0 1 15.75 21H5.25A2.25 2.25 0 0 1 3 18.75V8.25A2.25 2.25 0 0 1 5.25 6H10",
      title: "The agent can edit your local projects",
      description:
        "It can create and modify tasks, project settings, and other files in your project. We strongly recommend using git so you can review or revert changes.",
    },
    {
      icon: "M12 6v12m-3-2.818.879.659c1.171.879 3.07.879 4.242 0 1.172-.879 1.172-2.303 0-3.182C13.536 12.219 12.768 12 12 12c-.725 0-1.45-.22-2.003-.659-1.106-.879-1.106-2.303 0-3.182s2.9-.879 4.006 0l.415.33M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z",
      title: "Chat actions may consume API tokens",
      description:
        "The agent may run tasks, evals, and other API calls that use your token balance.",
    },
  ]
</script>

<Dialog
  bind:this={dialog}
  title="Enable Kiln Chat?"
  subtitle="Kiln Chat is an AI agent that can answer questions about your projects and make changes on your behalf."
  action_buttons={[
    { label: "Cancel", isCancel: true },
    { label: "Agree & Enable", isPrimary: true, action: approve },
  ]}
  on:cancel={() => dismiss()}
  on:close={() => dismiss()}
>
  <div class="flex flex-col gap-2.5">
    {#each items as item}
      <div class="flex items-start gap-3 rounded-lg bg-base-200/60 px-4 py-3">
        <div
          class="flex size-8 shrink-0 items-center justify-center rounded-full bg-base-300/80"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
            stroke-width="1.5"
            stroke="currentColor"
            class="size-4 text-base-content/70"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              d={item.icon}
            />
          </svg>
        </div>
        <div class="pt-0.5">
          <p class="text-sm font-medium leading-tight">{item.title}</p>
          <p class="text-xs text-gray-500 leading-relaxed mt-1">
            {item.description}
          </p>
        </div>
      </div>
    {/each}
  </div>
</Dialog>
