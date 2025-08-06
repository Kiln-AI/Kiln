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
          d="M22 13V12C22 8.22876 22 6.34315 20.8284 5.17157C19.6569 4 17.7712 4 14 4H10C6.22876 4 4.34315 4 3.17157 5.17157C2 6.34315 2 8.22876 2 12C2 15.7712 2 17.6569 3.17157 18.8284C4.34315 20 6.22876 20 10 20H13"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linecap="round"
        />
        <path
          d="M10 16H6"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linecap="round"
        />
        <path
          d="M2 10L22 10"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linecap="round"
        />
        <circle
          cx="18"
          cy="17"
          r="3"
          stroke="currentColor"
          stroke-width="1.5"
        />
        <path
          d="M20.5 19.5L21.5 20.5"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linecap="round"
        />
      </svg>
    </div>
    <div class="font-medium text-lg">
      Add RAG Configurations to Your Project
    </div>
    <div>
      Configure your RAG configuration to use your documents in your Kiln Tasks.
    </div>
    <div>
      Combine extractors, chunkers, embeddings and retrievers to create a RAG
      configuration.
    </div>

    <a
      class="btn btn-primary"
      href={`/docs/rag_configs/${project_id}/create_rag_config`}
      >Create RAG Configuration</a
    >
  </div>
</div>
