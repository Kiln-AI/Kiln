<script lang="ts">
  import { goto } from "$app/navigation"
  import { page } from "$app/stores"
  import { progress_ui_state as state } from "$lib/stores/progress_ui_store"

  function openLink() {
    if ($state?.link) {
      goto($state.link)
      close()
    }
  }

  function close() {
    $state = null
  }

  // Automatically close if they navigate to the link on their own
  // We need to track if we've left the page as we don't want to immediately close if they have not navigated away yet
  let has_left_target_page = false
  function track_link_change(_: string | undefined) {
    has_left_target_page = false
  }
  $: track_link_change($state?.link)
  function track_url_change(page_url: string) {
    if (has_left_target_page && page_url === $state?.link) {
      close()
    }
    if (page_url !== $state?.link) {
      has_left_target_page = true
    }
  }
  $: track_url_change($page.url.pathname)
</script>

{#if $state}
  <button
    class="bg-white border border-primary flex flex-col gap-1 items-start relative text-xs"
    on:click={openLink}
  >
    <button
      class="hover:text-xl h-8 w-8 leading-none absolute top-0 right-0 flex items-center justify-center"
      aria-label="Close progress notification"
      on:click={close}>&#x2715;</button
    >
    <div class="font-medium pr-6">
      {$state?.title}
    </div>
    <div class="font-light">
      {$state?.body}
      <a href={$state?.link} class="text-primary font-medium">{$state?.cta}</a>.
    </div>
    {#if $state?.progress !== null}
      <progress
        class="progress progress-primary w-full mt-1"
        value={$state.progress * 100}
        max="100"
      ></progress>
    {:else if $state?.step_count !== null && $state?.current_step !== null}
      <div class="h-4 overflow-hidden w-48 mt-1 ml-[-8px]">
        <div class="scale-[0.35] origin-top-left w-[160]">
          <ul class="steps pl-0 ml-0">
            {#each Array($state.step_count) as _, index}
              <li
                class="step {$state.step_count <= 6
                  ? 'w-[90px]'
                  : ''} {$state.current_step > index ? 'step-primary' : ''}"
                data-content=""
              >
                &nbsp;
              </li>
            {/each}
          </ul>
        </div>
      </div>
    {:else}
      <div class="badge badge-primary text-xs">In Progress</div>
    {/if}
  </button>
{/if}
