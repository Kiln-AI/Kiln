<script lang="ts">
  import {
    app_version,
    update_update_store,
    update_info,
  } from "$lib/utils/update"
  import AppPage from "../../app_page.svelte"
  import { onMount } from "svelte"
  import { _ } from "svelte-i18n"

  onMount(() => {
    update_update_store()
  })
</script>

<AppPage
  title={$_("updates.check_for_update")}
  sub_subtitle={$_("updates.current_version") + " " + app_version}
>
  <div>
    {#if $update_info.update_loading}
      <div class="w-full min-h-[50vh] flex justify-center items-center">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else if $update_info.update_result && $update_info.update_result.has_update}
      <div class="text-lg font-medium">{$_("updates.update_available")}</div>
      <div class="text-gray-500">
        {$_("common.version")}
        {$update_info.update_result.latest_version}
        {$_("updates.version_available")}
      </div>
      <a
        href={$update_info.update_result.link}
        class="btn btn-primary min-w-[180px] mt-6"
        target="_blank">{$_("updates.download_update")}</a
      >
    {:else if $update_info.update_result && !$update_info.update_result.has_update}
      <div class="text-lg font-medium">{$_("updates.no_update_available")}</div>
      <div class="text-gray-500">{$_("updates.latest_version")}</div>
    {:else}
      <div class="text-lg font-medium">{$_("updates.error_checking")}</div>
      <div class="text-error">{$update_info.update_error?.message}</div>
    {/if}
  </div>
</AppPage>
