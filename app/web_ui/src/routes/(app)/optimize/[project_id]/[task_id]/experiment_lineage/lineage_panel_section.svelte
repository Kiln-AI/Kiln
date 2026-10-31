<script lang="ts">
  export let title: string
</script>

<!-- The sidebar section title of the spec and run pages, the same style as
     PropertyList's own title. -->
<section class="flex flex-col gap-4">
  <div class="flex flex-col">
    <h2 class="text-xl font-bold">{title}</h2>
    <slot name="subtitle" />
  </div>
  <slot />
</section>
