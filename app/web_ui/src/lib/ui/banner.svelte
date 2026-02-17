<script lang="ts">
  export let href: string
  export let title: string
  export let description: string
  export let button_label: string
</script>

<a {href} class="group block">
  <div class="card border p-3 rounded-md hover:bg-gray-50">
    <div class="flex flex-row gap-4 items-center">
      <slot name="icon" />

      <div class="flex-grow flex flex-col text-sm justify-center">
        <span class="font-medium text-base">{title}</span>
        <span class="text-sm font-light mt-1">{description}</span>
        <div
          class="btn btn-xs btn-outline w-fit px-6 mt-2 group-hover:bg-secondary group-hover:text-secondary-content"
        >
          {button_label}
        </div>
      </div>
    </div>
  </div>
</a>
