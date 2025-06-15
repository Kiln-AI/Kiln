<script lang="ts">
  export let title: string
  export let small: boolean = true
</script>

<div
  class="collapse collapse-arrow bg-base-200 {small ? 'collapse-sm' : ''}"
  style="overflow: visible;"
>
  <input type="checkbox" class="peer min-h-[24px]" />
  <div
    class="collapse-title font-medium flex items-center text-sm min-h-[24px]"
  >
    {title}
  </div>
  <div class="collapse-content flex flex-col gap-4">
    <slot />
  </div>
</div>

<style>
  .collapse-sm input {
    max-height: 44px;
  }

  .collapse-sm .collapse-title::after {
    top: 1.4rem;
  }

  .collapse-sm .collapse-title {
    padding-top: 12px;
    padding-bottom: 12px;
  }
</style>
