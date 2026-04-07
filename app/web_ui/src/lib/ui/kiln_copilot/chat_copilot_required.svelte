<script lang="ts">
  import CopilotRequiredCard from "./copilot_required_card.svelte"

  export let compact: boolean = false
</script>

<CopilotRequiredCard
  description_markdown="Get AI assistance for your tasks and projects.\n**Kiln Chat requires a Kiln Copilot paid plan.**"
  auth_href="/chat/copilot_auth"
  learn_more_label="Learn More"
  learn_more_href="https://docs.kiln.tech"
  {compact}
/>
