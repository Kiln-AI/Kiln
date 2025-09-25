<script lang="ts">
  import type { ActionButton } from "../../routes/(app)/types"
  import ButtonList from "./button_list.svelte"

  type MultiIntro = {
    title: string
    description: string
    action_buttons: ActionButton[]
  }

  export let intros: MultiIntro[]
</script>

<!-- Desktop version -->
<div
  class="hidden md:flex flex-col items-center justify-center min-h-[50vh] mt-12"
>
  <div class="flex justify-center">
    <!-- Hidden div to force the compiler to find these classes -->
    <span
      class="hidden grid-cols-2 grid-cols-1 grid-cols-3 grid-cols-4 grid-cols-5 grid-cols-6 grid-cols-7 grid-cols-8 grid-cols-9 grid-cols-10"
    ></span>
    <div
      class="grid gap-x-32 gap-y-4 items-start font-light text-sm"
      style="grid-template-columns: {intros.map(() => '270px').join(' ')};"
    >
      <!-- Icons Row -->
      {#each intros as _, index}
        <div class="text-center">
          <div class="flex justify-center">
            <!-- Ugly but required -->
            {#if index === 0}
              <slot name="image-0" />
            {:else if index === 1}
              <slot name="image-1" />
            {:else if index === 2}
              <slot name="image-2" />
            {:else if index === 3}
              <slot name="image-3" />
            {:else if index === 4}
              <slot name="image-4" />
            {:else if index === 5}
              <slot name="image-5" />
            {:else if index === 6}
              <slot name="image-6" />
            {:else if index === 7}
              <slot name="image-7" />
            {:else if index === 8}
              <slot name="image-8" />
            {:else if index === 9}
              <slot name="image-9" />
            {:else}
              <!-- Default fallback for more than 10 items -->
              <div
                class="w-12 h-12 bg-gray-200 rounded-full flex items-center justify-center"
              ></div>
            {/if}
          </div>
        </div>
      {/each}

      <!-- Titles Row -->
      {#each intros as intro}
        <div class="text-center">
          <h2 class="font-medium text-lg">{intro.title}</h2>
        </div>
      {/each}

      <!-- Descriptions Row -->
      {#each intros as intro}
        <div class="">
          <p class="">{intro.description}</p>
        </div>
      {/each}

      <!-- Action Buttons Row -->
      {#each intros as intro}
        <ButtonList buttons={intro.action_buttons} />
      {/each}
    </div>
  </div>
</div>

<!-- Mobile version -->
<div class="flex md:hidden flex-col mt-12 gap-y-12">
  {#each intros as intro}
    <div class="flex flex-col">
      <h2 class="font-medium text-lg mb-1">{intro.title}</h2>
      <p class="font-light">{intro.description}</p>
      <ButtonList buttons={intro.action_buttons} />
    </div>
  {/each}
</div>
