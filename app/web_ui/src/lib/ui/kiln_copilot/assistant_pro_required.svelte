<script lang="ts">
  import CopilotRequiredCard from "./copilot_required_card.svelte"

  export let compact: boolean = false
</script>

<CopilotRequiredCard
  title="Kiln Assistant"
  description_markdown="Kiln Assistant helps you build, evaluate, and optimize your AI systems."
  auth_href="/assistant/pro_auth"
  {compact}
  connect_button_label="Log in to Kiln"
  icon="chat"
/>
