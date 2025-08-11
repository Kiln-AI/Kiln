<script lang="ts">
  import Intro from "$lib/ui/intro.svelte"

  export let project_id: string
</script>

<div class="flex flex-col md:flex-row gap-32 justify-center items-center">
  <div class="max-w-[300px] font-light text-sm flex flex-col gap-4">
    <div class="flex justify-center items-center">
      <!-- Uploaded to: SVG Repo, www.svgrepo.com, Generator: SVG Repo Mixer Tools. Attribution: https://www.svgrepo.com/svg/524492/database -->
      <svg
        class="w-12 h-12"
        viewBox="0 0 24 24"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <path
          d="M18.6597 8.2861L19.028 7.91787C19.3704 7.57542 19.5416 7.4042 19.6445 7.22608C19.9236 6.74271 19.9236 6.14718 19.6445 5.66381C19.5416 5.48569 19.3704 5.31446 19.028 4.97202C18.6855 4.62957 18.5143 4.45835 18.3362 4.35551C17.8528 4.07644 17.2573 4.07644 16.7739 4.35551C16.5958 4.45835 16.4246 4.62957 16.0821 4.97202L15.7139 5.34025M11.2951 15.6507L5.77166 21.1742C5.42921 21.5166 5.25799 21.6879 5.07987 21.7907C4.5965 22.0698 4.00097 22.0698 3.5176 21.7907C3.33948 21.6879 3.16825 21.5166 2.82581 21.1742C2.48337 20.8317 2.31214 20.6605 2.2093 20.4824C1.93023 19.999 1.93023 19.4035 2.2093 18.9201C2.31214 18.742 2.48337 18.5708 2.82581 18.2283L8.34928 12.7049M7.61281 11.9684L12.0316 16.3872C13.7674 18.123 14.6354 18.991 15.7139 18.991C16.7924 18.991 17.6604 18.123 19.3962 16.3872C21.1321 14.6513 22 13.7834 22 12.7049C22 11.6263 21.1321 10.7584 19.3962 9.02256L14.9774 4.60379C13.2416 2.86793 12.3737 2 11.2951 2C10.2166 2 9.34867 2.86793 7.61281 4.60379C5.87696 6.33965 5.00903 7.20757 5.00903 8.2861C5.00903 9.36462 5.87696 10.2326 7.61281 11.9684Z"
          stroke="currentColor"
          stroke-width="1.5"
        />
      </svg>
    </div>
    <Intro
      title="Add Tools to Your Project"
      description_paragraphs={[
        "Tools can provide powerful capabilities to your AI tasks.",
        "To get started, add MCP servers to give your system new skills.",
      ]}
      action_buttons={[
        {
          label: "Add Tool",
          href: `/settings/manage_tools/${project_id}/add_tools`,
          is_primary: true,
        },
      ]}
    />
  </div>
</div>
