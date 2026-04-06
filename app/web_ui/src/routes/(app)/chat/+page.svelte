<script lang="ts">
  import { getContext, onDestroy } from "svelte"
  import type { Writable } from "svelte/store"
  import AppPage from "../app_page.svelte"
  import Chat from "./chat.svelte"
  import { agentInfo } from "$lib/agent"
  import type { ActionButton } from "$lib/types"

  agentInfo.set({
    name: "Chat",
    description: "The chat interface for conversing with the AI assistant.",
  })

  let chatRef: Chat
  let hasMessages = false

  $: action_buttons = [
    ...(hasMessages
      ? [
          {
            icon: "/images/new_chat.svg",
            handler: () => chatRef?.newChat(),
          } as ActionButton,
        ]
      : []),
    {
      icon: "/images/history.svg",
      handler: () => chatRef?.openHistory(),
    },
  ]

  const noLayoutBottomPadding = getContext<Writable<boolean>>(
    "noLayoutBottomPadding",
  )
  noLayoutBottomPadding.set(true)
  onDestroy(() => noLayoutBottomPadding.set(false))
</script>

<AppPage title="Chat" no_y_padding={true} {action_buttons}>
  <div class="flex flex-col h-[calc(100vh-8rem)] pt-4">
    <Chat bind:this={chatRef} bind:hasMessages />
  </div>
</AppPage>
