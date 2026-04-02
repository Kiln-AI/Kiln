<script lang="ts">
  import AppPage from "../app_page.svelte"
  import Chat from "./chat.svelte"
  import EmptyChat from "./empty_chat.svelte"
</script>

<AppPage
  title="Chat"
  subtitle="Streaming chat"
  limit_max_width={true}
  no_y_padding={true}
>
  <EmptyChat />
  <Chat />
</AppPage>
