<script lang="ts">
  import type { ActionButton } from "$lib/types"
  import ButtonList from "./button_list.svelte"

  type MultiIntro = {
    title: string
    description: string
    action_buttons: ActionButton[]
  }

  export let intros: MultiIntro[]

  let containerWidth = 0
  $: showDesktop = containerWidth >= 300 * intros.length
</script>

<div bind:clientWidth={containerWidth}>
  {#if showDesktop}
    <!-- Desktop version -->
    <div class="flex flex-col items-center justify-center min-h-[50vh] mt-8">
      <div class="flex justify-center w-full px-2">
        <div
          class="grid w-full gap-y-4 items-start font-light text-sm"
          style="grid-template-columns: {intros
            .map(() => '270px')
            .join(' ')}; justify-content: space-evenly;"
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
  {:else}
    <!-- Mobile version -->
    <div class="flex flex-col mt-2 gap-y-12">
      {#each intros as intro}
        <div class="flex flex-col">
          <h2 class="font-medium text-lg mb-1">{intro.title}</h2>
          <p class="font-light">{intro.description}</p>
          <ButtonList buttons={intro.action_buttons} />
        </div>
      {/each}
    </div>
  {/if}
</div>
