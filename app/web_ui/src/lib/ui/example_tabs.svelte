<script lang="ts">
  export let examples: { label: string; code: string }[]
  export let active_index: number = 0

  const id_prefix = "example_tabs_" + Math.random().toString(36).slice(2)

  let tab_buttons: HTMLButtonElement[] = []

  function select_and_focus(index: number) {
    active_index = index
    tab_buttons[index]?.focus()
  }

  function on_tab_keydown(event: KeyboardEvent, index: number) {
    // Leave browser/OS shortcuts alone (Alt+Left is Back on Windows/Linux).
    if (event.altKey || event.ctrlKey || event.metaKey) {
      return
    }
    const last = examples.length - 1
    switch (event.key) {
      case "ArrowRight":
        select_and_focus(index === last ? 0 : index + 1)
        break
      case "ArrowLeft":
        select_and_focus(index === 0 ? last : index - 1)
        break
      case "Home":
        select_and_focus(0)
        break
      case "End":
        select_and_focus(last)
        break
      default:
        return
    }
    event.preventDefault()
  }
</script>

<div class="flex flex-col gap-4">
  <!-- DaisyUI v4 sets .tabs to display:grid, which keeps every tab on one
       row. flex + flex-wrap lets long labels wrap instead of being clipped. -->
  <!-- tabs-md is the explicit default size: tabs-sm shrinks the pill to 24px,
       where DaisyUI's outline-offset:-5px focus ring cuts through the label. -->
  <div
    role="tablist"
    aria-label="Examples"
    class="tabs tabs-boxed tabs-md flex flex-wrap gap-1 w-fit max-w-full"
  >
    {#each examples as example, i}
      <button
        bind:this={tab_buttons[i]}
        type="button"
        role="tab"
        id="{id_prefix}_tab_{i}"
        aria-selected={active_index === i}
        aria-controls="{id_prefix}_panel"
        tabindex={active_index === i ? 0 : -1}
        class="tab min-w-0 justify-start {active_index === i
          ? 'tab-active'
          : ''}"
        on:click={() => (active_index = i)}
        on:keydown={(event) => on_tab_keydown(event, i)}
      >
        <!-- Truncation needs a block container: text-overflow does nothing on
             the flex container .tab itself. -->
        <span class="truncate">{example.label}</span>
      </button>
    {/each}
  </div>
  <!-- tabindex so keyboard users can scroll the code block (WCAG 2.1.1). -->
  <div
    role="tabpanel"
    id="{id_prefix}_panel"
    aria-labelledby="{id_prefix}_tab_{active_index}"
    tabindex="0"
    class="bg-base-200 rounded-lg p-4 overflow-x-auto font-mono text-sm whitespace-pre"
  >
    {examples[active_index]?.code ?? ""}
  </div>
</div>
