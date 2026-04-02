<script lang="ts">
  import AppPage from "../app_page.svelte"
  import Chat from "./chat.svelte"
</script>

<AppPage title="Chat" full_height={true} no_y_padding={true}>
  <div class="flex flex-col flex-1 min-h-0 pt-8">
    <Chat />
  </div>
</AppPage>
