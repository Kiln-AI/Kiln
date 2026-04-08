<script lang="ts">
  import { onDestroy } from "svelte"

  const verbs = [
    "Firing",
    "Glazing",
    "Tempering",
    "Kilning",
    "Kilning it",
    "Smelting",
    "Forging",
    "Stoking",
    "Kindling",
    "Molding",
    "Quenching",
    "Sintering",
    "Burnishing",
    "Bellowing",
    "Vitrifying",
    "Throwing",
    "Bisqueing",
    "Crucibleing",
    "Casting",
    "Slagging",
    "Bellowsing",
    "Refining",
    "Carbonizing",
    "Enameling",
    "Curing",
    "Sculpting",
    "Smoldering",
    "Baking",
    "Chiseling",
    "Etching",
    "Torching",
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
