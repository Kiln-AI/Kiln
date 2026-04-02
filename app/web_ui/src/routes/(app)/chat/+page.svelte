<script lang="ts">
  import { getContext, onDestroy } from "svelte"
  import type { Writable } from "svelte/store"
  import AppPage from "../app_page.svelte"
  import Chat from "./chat.svelte"

  const noLayoutBottomPadding = getContext<Writable<boolean>>(
    "noLayoutBottomPadding",
  )
  noLayoutBottomPadding.set(true)
  onDestroy(() => noLayoutBottomPadding.set(false))
</script>

<AppPage title="Chat" no_y_padding={true}>
  <div class="flex flex-col h-[calc(100vh-8rem)] pt-4">
    <Chat />
  </div>
</AppPage>
