<script lang="ts">
  import type { RatingType } from "$lib/types"
  import { createEventDispatcher } from "svelte"
  const dispatch = createEventDispatcher()
  export let rating: number | null = null
  export let type: RatingType
  let hover_rating: number | null = null
  let id = Math.random().toString(36)
  export let size: number = 8

  $: visual_rating = hover_rating ? hover_rating : rating

  function rating_clicked(new_rating: number) {
    // click current to remove rating
    if (new_rating === rating) {
      rating = null
    } else {
      rating = new_rating
    }
    dispatch("rating_changed", { rating: new_rating })
  }
</script>

<div class="rating" {id}>
  {#if type === "five_star"}
    <!-- For the compiler so our sizes aren't compiled away -->
    <p class="hidden h-5 w-5 h-6 w-6 h-7 w-7 h-8 w-8"></p>
    <input
      type="radio"
      name="rating-{id}"
      class="rating-hidden"
      checked={visual_rating === null}
      value={null}
      bind:group={rating}
    />
    {#each [1, 2, 3, 4, 5] as r}
      <input
        type="radio"
        name="rating-{id}"
        class="mask mask-star-2 w-{size} h-{size}"
        checked={visual_rating === r}
        on:mouseover={() => (hover_rating = r)}
        on:focus={() => (hover_rating = r)}
        on:mouseleave={() => (hover_rating = null)}
        on:blur={() => (hover_rating = null)}
        on:click={() => rating_clicked(r)}
        value={r}
        bind:group={rating}
      />
    {/each}
  {:else if type === "custom"}
    <div class="text-sm text-gray-500 pl-2">
      Custom type not supported in UI
    </div>
  {:else if type === "pass_fail_critical" || type === "pass_fail"}
    <div class="flex flex-row gap-1 ml-1">
      <button
        class="btn btn-sm btn-outline hover:btn-success {rating === 1
          ? 'btn-secondary'
          : 'text-base-content/40'}"
        on:click={() => rating_clicked(1)}>Pass</button
      >
      <button
        class="btn btn-sm btn-outline hover:btn-warning {rating === 0
          ? 'btn-secondary'
          : 'text-base-content/40'}"
        on:click={() => rating_clicked(0)}>Fail</button
      >
      {#if type === "pass_fail_critical"}
        <button
          class="btn btn-sm btn-outline hover:btn-error {rating === -1
            ? 'btn-secondary'
            : 'text-base-content/40'}"
          on:click={() => rating_clicked(-1)}>Critical</button
        >
      {/if}
    </div>
  {/if}
</div>
