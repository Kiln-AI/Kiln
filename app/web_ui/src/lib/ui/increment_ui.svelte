<script lang="ts">
  export let value: number
  export let min: number = 1
  export let max: number = 50

  function clamp(n: number): number {
    // A blank or unparseable entry falls back to the minimum rather than NaN.
    if (!Number.isFinite(n)) return min
    return Math.min(max, Math.max(min, Math.round(n)))
  }

  // `text` is what's in the box; `value` is what's in effect. They're kept in
  // step by set_value, and `last_value` lets us tell an external change (a
  // stepper, or the parent rebinding) from one we made ourselves while typing —
  // so we never rewrite the box mid-keystroke.
  let text = String(value)
  let last_value = value

  $: if (value !== last_value) {
    last_value = value
    text = String(value)
  }

  function set_value(n: number) {
    value = n
    last_value = n
  }

  function on_input() {
    // Digits only. parseInt would happily accept "12abc" as 12, so strip
    // anything non-numeric out of the box as it's typed or pasted.
    const digits = text.replace(/\D/g, "")
    if (digits !== text) {
      text = digits
    }
    if (digits === "") {
      // Cleared mid-edit — leave it empty so it stays editable; blur settles it.
      return
    }
    const n = parseInt(digits, 10)
    if (!Number.isFinite(n)) {
      return
    }
    if (n > max) {
      // Clamp down to the cap immediately, so typing 9999 lands on 500 rather
      // than waiting for blur.
      text = String(max)
      set_value(max)
      return
    }
    if (n >= min) {
      set_value(n)
    }
    // Below min (e.g. a lone "0" on the way to "50") is left for blur, so the
    // box stays editable.
  }

  function commit() {
    const n = clamp(parseInt(text, 10))
    text = String(n)
    set_value(n)
  }

  function step(delta: number) {
    const n = clamp(value + delta)
    text = String(n)
    set_value(n)
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
    on:input={on_input}
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
