<script lang="ts">
  export let title: string
  export let promos: string[]
  export let image_path: string
</script>

<div class="flex flex-col gap-4">
  <div class="flex flex-col md:flex-row gap-12">
    <div class="flex-1 flex flex-col gap-8 place-self-center">
      <p class="text-2xl font-light">{title}</p>
      {#each promos as promo}
        <p class="text-gray-500">{promo}</p>
      {/each}
    </div>
    <div class="flex-1">
      <img src={image_path} alt={title} class="max-w-[300px] mx-auto" />
    </div>
  </div>
</div>
