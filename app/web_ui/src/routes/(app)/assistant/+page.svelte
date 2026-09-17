<script lang="ts">
  import { getContext, onDestroy, onMount } from "svelte"
  import type { Writable } from "svelte/store"
  import AppPage from "../app_page.svelte"
  import Chat from "./chat.svelte"
  import { agentInfo } from "$lib/agent"
  import type { ActionButton } from "$lib/types"
  import AssistantProRequired from "$lib/ui/kiln_copilot/assistant_pro_required.svelte"
  import {
    kilnCopilotConnected,
    initCopilotConnectionStore,
  } from "$lib/stores/copilot_connection_store"

  const chatPageTitle = "Assistant"

  agentInfo.set({
    name: "Assistant",
    description:
      "The interface for conversing with the Kiln Assistant AI agent.",
  })

  let chatRef: Chat
  let hasMessages = false

  $: action_buttons =
    $kilnCopilotConnected !== true
      ? ([] as ActionButton[])
      : [
          ...(hasMessages
            ? [
                {
                  label: "New Chat",
                  icon: "/images/new_chat.svg",
                  handler: () => chatRef?.newChat(),
                } as ActionButton,
              ]
            : []),
          {
            label: "History",
            icon: "/images/history.svg",
            handler: () => chatRef?.openHistory(),
          },
        ]

  const noLayoutBottomPadding = getContext<Writable<boolean>>(
    "noLayoutBottomPadding",
  )
  noLayoutBottomPadding.set(true)
  onDestroy(() => noLayoutBottomPadding.set(false))

  onMount(() => {
    initCopilotConnectionStore()
  })
</script>

<AppPage title={chatPageTitle} no_y_padding={true} {action_buttons}>
  <div class="flex flex-col h-[calc(100vh-8rem)] pt-4">
    {#if $kilnCopilotConnected === null}
      <div class="w-full min-h-[50vh] flex justify-center items-center">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else if $kilnCopilotConnected === false}
      <AssistantProRequired />
    {:else}
      <Chat bind:this={chatRef} bind:hasMessages />
    {/if}
  </div>
</AppPage>
