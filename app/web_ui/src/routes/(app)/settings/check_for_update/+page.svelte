<script lang="ts">
  import {
    app_version,
    update_update_store,
    update_info,
  } from "$lib/utils/update"
  import AppPage from "../../app_page.svelte"
  import { onMount } from "svelte"

  onMount(() => {
    update_update_store()
  })
</script>

<AppPage
  title="Check for Update"
  sub_subtitle={`Current Version ${app_version}`}
>
  <div>
    {#if $update_info.update_loading}
      <div class="w-full min-h-[50vh] flex justify-center items-center">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else if $update_info.update_result && $update_info.update_result.has_update}
      <div class="text-lg font-medium">Update Available</div>
      <div class="text-gray-500">
        Version {$update_info.update_result.latest_version} is available.
      </div>
      <a
        href={$update_info.update_result.link}
        class="btn btn-primary min-w-[180px] mt-6"
        target="_blank">Download Update</a
      >
    {:else if $update_info.update_result && !$update_info.update_result.has_update}
      <div class="text-lg font-medium">No Update Available</div>
      <div class="text-gray-500">You are using the latest version of Kiln.</div>
    {:else}
      <div class="text-lg font-medium">Error Checking for Update</div>
      <div class="text-error">{$update_info.update_error?.message}</div>
    {/if}
  </div>
</AppPage>
