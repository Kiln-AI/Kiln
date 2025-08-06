<script lang="ts">
  import Checkmark from "./checkmark.svelte"

  export let title: string
  export let subtitle: string
  export let link: string
  export let button_text: string
</script>

<div
  class="w-full min-h-[50vh] flex flex-col justify-center items-center gap-2"
>
  <Checkmark classOverride="size-10 text-success mb-2" />
  <div class="font-medium mb-2">{title}</div>
  <div class="max-w-96 text-center font-light">
    {subtitle}
    <div class="mt-8">
      <a href={link} class="btn btn-primary btn-wide">
        {button_text}
      </a>
    </div>
  </div>
</div>
