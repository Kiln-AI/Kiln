<script lang="ts">
  import { goto } from "$app/navigation"
  import { agentInfo } from "$lib/agent"

  agentInfo.set({
    name: "Home Redirect",
    description: "Redirects to the Run page.",
  })
  goto("/run")
</script>
