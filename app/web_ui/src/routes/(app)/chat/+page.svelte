<script lang="ts">
  import AppPage from "../app_page.svelte"
  import Chat from "./chat.svelte"
</script>

<AppPage
  title="Chat"
  subtitle="Streaming chat"
  full_height={true}
  no_y_padding={true}
>
  <div class="flex flex-col flex-1 min-h-0 mt-8">
    <Chat />
  </div>
</AppPage>
