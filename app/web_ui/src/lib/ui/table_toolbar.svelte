<script lang="ts">
  export let select_mode: boolean = false
  export let selected_count: number = 0
  export let filter_tags_count: number = 0
  export let onToggleSelectMode: () => void = () => {}
  export let onCancelSelection: () => void = () => {}
  export let onShowFilterDialog: () => void = () => {}
  export let onShowAddTags: () => void = () => {}
  export let onShowRemoveTags: () => void = () => {}
  export let onShowDelete: (() => void) | undefined = undefined
</script>

<div
  class="mb-4 flex flex-row items-center justify-end py-2 gap-3 {select_mode
    ? 'sticky top-0 z-10 backdrop-blur'
    : ''}"
>
  {#if select_mode}
    <div class="font-light text-sm">
      {selected_count} selected
    </div>
    {#if selected_count > 0}
      <div class="dropdown dropdown-end">
        <div tabindex="0" role="button" class="btn btn-mid !px-3">
          <img alt="tags" src="/images/tag.svg" class="w-5 h-5" />
        </div>
        <ul
          class="dropdown-content menu bg-base-100 rounded-box z-[1] w-52 p-2 shadow"
        >
          <li>
            <button tabindex="0" on:click={onShowAddTags}> Add Tags </button>
          </li>
          <li>
            <button tabindex="0" on:click={onShowRemoveTags}>
              Remove Tags
            </button>
          </li>
        </ul>
      </div>
      {#if onShowDelete}
        <button class="btn btn-mid !px-3" on:click={onShowDelete}>
          <img alt="delete" src="/images/delete.svg" class="w-5 h-5" />
        </button>
      {/if}
    {/if}
    <button class="btn btn-mid" on:click={onCancelSelection}>
      Cancel Selection
    </button>
  {:else}
    <button class="btn btn-mid" on:click={onToggleSelectMode}> Select </button>
    <button class="btn btn-mid !px-3" on:click={onShowFilterDialog}>
      <img alt="filter" src="/images/filter.svg" class="w-5 h-5" />
      {#if filter_tags_count > 0}
        <span class="badge badge-primary badge-sm">{filter_tags_count}</span>
      {/if}
    </button>
  {/if}
</div>
