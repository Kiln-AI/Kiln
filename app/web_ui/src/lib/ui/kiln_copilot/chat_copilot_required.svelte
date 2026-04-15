<script lang="ts">
  import CopilotRequiredCard from "./copilot_required_card.svelte"

  export let compact: boolean = false
</script>

<CopilotRequiredCard
  title="Kiln Chat"
  description_markdown="Chat with Kiln to build, evaluate, and optimize your AI systems."
  auth_href="/chat/copilot_auth"
  {compact}
  connect_button_label="Log in"
  icon="chat"
/>
