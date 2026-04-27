<script lang="ts">
  import { onDestroy } from "svelte"

  const verbs = [
    "Baking",
    "Bellowing",
    "Bisquing",
    "Burnishing",
    "Carbonizing",
    "Casting",
    "Chiseling",
    "Crucibleing",
    "Curing",
    "Enameling",
    "Etching",
    "Firing",
    "Forging",
    "Glazing",
    "Kilning",
    "Kilning it",
    "Kindling",
    "Molding",
    "Quenching",
    "Refining",
    "Sculpting",
    "Sintering",
    "Slagging",
    "Smoldering",
    "Stoking",
    "Tempering",
    "Throwing",
    "Torching",
    "Trimming",
    "Vitrifying",
  ]

  const verb = verbs[Math.floor(Math.random() * verbs.length)]

  let dotCount = 1
  const dotInterval = setInterval(() => {
    dotCount = (dotCount % 3) + 1
  }, 2000)
  onDestroy(() => clearInterval(dotInterval))
</script>

<div class="flex items-center py-0.5">
  <img src="/images/chat_icon_animated.svg" alt="loading..." class="w-9 h-9" />
  <span class="text-sm ml-2 text-gray-500">{verb}{".".repeat(dotCount)}</span>
</div>
