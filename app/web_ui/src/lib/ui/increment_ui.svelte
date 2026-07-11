<script lang="ts">
  export let value: number
  export let min: number = 1
  export let max: number = 50

  function clamp(n: number): number {
    // A blank or unparseable entry falls back to the minimum rather than NaN.
    if (!Number.isFinite(n)) return min
    return Math.min(max, Math.max(min, Math.round(n)))
  }

  // The box mirrors `value` as text so it can be typed into freely. It's only
  // committed (and clamped) on blur or Enter — otherwise a partial entry like
  // "" or "5" on the way to "50" would get rewritten mid-keystroke. Entries
  // above `max` clamp down to it, which is what the +/- buttons already do.
  let text = String(value)
  $: text = String(value)

  function commit() {
    value = clamp(parseInt(text, 10))
    // Re-sync, so a clamped or unparseable entry snaps to the value in effect.
    text = String(value)
  }

  function step(delta: number) {
    value = clamp(value + delta)
  }
</script>

<div class="flex flex-row gap-2 items-center">
  <button
    type="button"
    class="btn btn-sm"
    aria-label="Decrease"
    on:click={() => step(-1)}
  >
    -
  </button>
  <input
    type="text"
    inputmode="numeric"
    class="input input-sm input-bordered text-lg font-medium w-16 text-center px-1"
    aria-label="Count"
    bind:value={text}
    on:blur={commit}
    on:keydown={(e) => {
      if (e.key === "Enter") {
        // Don't let Enter submit the enclosing form before we've committed.
        e.preventDefault()
        commit()
      }
    }}
  />
  <button
    type="button"
    class="btn btn-sm"
    aria-label="Increase"
    on:click={() => step(1)}
  >
    +
  </button>
</div>
