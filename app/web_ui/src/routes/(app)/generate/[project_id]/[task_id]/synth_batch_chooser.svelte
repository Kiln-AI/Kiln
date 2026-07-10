<script lang="ts">
  export let on_manual: () => void
  export let on_kiln_pro: () => void

  const rows: { label: string; manual: string; pro: string }[] = [
    { label: "Batch planning", manual: "By hand", pro: "Automatic" },
    {
      label: "Per-input prompts",
      manual: "Write each one",
      pro: "Drafted for you",
    },
    { label: "Coverage across topics", manual: "Manual", pro: "Automatic" },
    {
      label: "Edge cases",
      manual: "You add them",
      pro: "Included deliberately",
    },
    { label: "Batch summary", manual: "—", pro: "Generated" },
    { label: "Approx. effort", manual: "~30 min", pro: "~2 min" },
    { label: "Kiln account", manual: "Optional", pro: "Required" },
  ]
</script>

<div class="my-4 max-w-[680px] mx-auto">
  <div class="text-center mt-8 mb-2">
    <div class="text-lg font-medium">Build your synthetic batch</div>
    <div class="text-sm text-gray-500 mt-1">
      Kiln Pro plans the batch for you — or build it yourself the classic way.
    </div>
  </div>

  <div class="overflow-x-auto">
    <table class="table w-full mt-4">
      <colgroup>
        <col class="w-[50%]" />
        <col class="w-[25%]" />
        <col class="w-[25%]" />
      </colgroup>
      <thead>
        <tr class="border-b-0">
          <th></th>
          <th class="text-center text-lg">Manual</th>
          <th class="text-center text-lg">
            <div class="flex items-center justify-center gap-2">
              <img
                src="/images/animated_logo.svg"
                alt="Kiln Pro"
                class="size-4"
              />
              <span>Kiln Pro</span>
            </div>
          </th>
        </tr>
      </thead>
      <tbody>
        {#each rows as row, i}
          <tr class={i === rows.length - 1 ? "border-b" : ""}>
            <th class="font-bold text-xs text-gray-500">{row.label}</th>
            <td class="text-center">{row.manual}</td>
            <td class="text-center border-l">{row.pro}</td>
          </tr>
        {/each}
        <tr>
          <th></th>
          <td class="text-center pt-4">
            <button
              class="btn btn-outline btn-sm whitespace-nowrap"
              on:click={on_manual}
            >
              Create Manually
            </button>
          </td>
          <td class="text-center pt-4">
            <button
              class="btn btn-primary btn-sm whitespace-nowrap"
              on:click={on_kiln_pro}
            >
              Use Kiln Pro
            </button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</div>
