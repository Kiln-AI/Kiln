<script lang="ts">
  export let project_id: string
</script>

<div class="flex flex-col md:flex-row gap-32 justify-center items-center">
  <div class="max-w-[300px] font-light text-sm flex flex-col gap-4">
    <div class="flex justify-center items-center">
      <!-- Uploaded to: SVG Repo, www.svgrepo.com, Generator: SVG Repo Mixer Tools -->
      <svg
        class="w-12 h-12"
        viewBox="0 0 24 24"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <path
          d="M12 21H13C16.7712 21 18.6569 21 19.8284 19.8284C21 18.6569 21 16.7712 21 13V11C21 7.22876 21 5.34315 19.8284 4.17157C18.6569 3 16.7712 3 13 3L12 3"
          stroke="currentColor"
          stroke-width="1.5"
        />
        <path
          d="M13 21H9C6.17157 21 4.75736 21 3.87868 20.1213C3 19.2426 3 17.8284 3 15L3 9C3 6.17157 3 4.75736 3.87868 3.87868C4.75736 3 6.17157 3 9 3L13 3"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linecap="round"
          stroke-dasharray="2.5 3"
        />
        <path
          d="M12 22L12 2"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linecap="round"
        />
      </svg>
    </div>
    <div class="font-medium text-lg">Add Extractors to Your Project</div>
    <div>Extract information from documents into a format LLMs can use.</div>
    <div>
      For example, an extractor can convert a PDF into markdown or a video into
      a transcript.
    </div>

    <a
      class="btn btn-primary"
      href={`/docs/extractors/${project_id}/create_extractor`}
      >Create Extractor</a
    >
  </div>
</div>
