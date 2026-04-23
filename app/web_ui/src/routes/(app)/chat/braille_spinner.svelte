<script lang="ts">
  import { onDestroy } from "svelte"

  const frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
  let index = 0
  const interval = setInterval(() => {
    index = (index + 1) % frames.length
  }, 80)
  onDestroy(() => clearInterval(interval))
</script>

<span class="inline-block w-3 text-center font-mono" aria-hidden="true"
  >{frames[index]}</span
>
