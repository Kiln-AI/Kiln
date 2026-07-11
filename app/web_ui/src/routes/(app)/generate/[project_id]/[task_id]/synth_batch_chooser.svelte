<script lang="ts">
  export let on_manual: () => void
  export let on_kiln_pro: () => void

  const rows: { label: string; manual: string; pro: string }[] = [
    { label: "Effort", manual: "15 mins", pro: "5 mins" },
    { label: "Use Case Coverage", manual: "Manual", pro: "AI Planned" },
    { label: "Edge Cases Coverage", manual: "Manual", pro: "AI Planned" },
    { label: "Kiln account", manual: "Optional", pro: "Required" },
  ]
</script>

<div class="mt-24 md:mt-36 mb-4 max-w-[680px] mx-auto">
  <div class="text-lg font-medium text-center mb-2">
    Build Synthetic Dataset
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
