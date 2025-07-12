<script lang="ts">
  import { page } from "$app/stores"
  import { onMount, tick } from "svelte"

  export let splits: Record<string, number>
  export let subtitle: string | undefined

  onMount(async () => {
    await tick()
    // Load from URL if not already set
    if (Object.keys(splits).length === 0) {
      splits = get_splits_from_url()
    }
  })

  function get_splits_from_url() {
    const splitsParam = $page.url.searchParams.get("splits")
    if (!splitsParam) return {}

    try {
      const splitMap: Record<string, number> = {}
      const pairs = splitsParam.split(",")

      for (const pair of pairs) {
        const [name, value] = pair.split(":").map((s) => s.trim())
        const numValue = parseFloat(value)
        if (isNaN(numValue) || numValue < 0 || numValue > 1) {
          throw new Error("Invalid split value")
        }
        splitMap[name] = numValue
      }

      // Validate that splits sum to 1
      const total = Object.values(splitMap).reduce((sum, val) => sum + val, 0)
      if (Math.abs(total - 1) > 0.001) {
        throw new Error("Split values must sum to 1")
      }

      return splitMap
    } catch (e) {
      console.warn("Invalid splits parameter, using default", e)
      return {}
    }
  }

  $: subtitle = (() => {
    if (Object.keys(splits).length === 0) return undefined
    return `Samples will be assigned the following tags: ${Object.entries(
      splits,
    )
      .map(([name, value]) => `${Math.round(value * 100)}% ${name}`)
      .join(", ")}`
  })()

  export function get_random_split_tag() {
    if (Object.keys(splits).length === 0) return undefined

    const random = Math.random()
    let cumulative = 0

    for (const [tag, probability] of Object.entries(splits)) {
      cumulative += probability
      if (random <= cumulative) {
        return tag
      }
    }

    // Fallback (should never reach here if splits sum to 1)
    return Object.keys(splits)[0]
  }
</script>
