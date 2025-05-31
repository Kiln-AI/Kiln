<script lang="ts">
  import { page } from "$app/stores"
  import { _ } from "svelte-i18n"

  export let generate_subtopics: () => void
  export let generate_samples: () => void
  export let project_id: string
  export let task_id: string

  let let_me_in: boolean = false
  $: reason = $page.url.searchParams.get("reason")
</script>

<div class="flex flex-col md:flex-row gap-32 justify-center items-center">
  <div class="max-w-[300px] font-light text-sm flex flex-col gap-4">
    <div class="flex justify-center items-center">
      <!-- Uploaded to: SVG Repo, www.svgrepo.com, Generator: SVG Repo Mixer Tools -->
      <svg
        class="w-10 h-10"
        viewBox="0 0 24 24"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <path
          d="M22 10.5V12C22 16.714 22 19.0711 20.5355 20.5355C19.0711 22 16.714 22 12 22C7.28595 22 4.92893 22 3.46447 20.5355C2 19.0711 2 16.714 2 12C2 7.28595 2 4.92893 3.46447 3.46447C4.92893 2 7.28595 2 12 2H13.5"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linecap="round"
        />
        <path
          d="M16.652 3.45506L17.3009 2.80624C18.3759 1.73125 20.1188 1.73125 21.1938 2.80624C22.2687 3.88124 22.2687 5.62415 21.1938 6.69914L20.5449 7.34795M16.652 3.45506C16.652 3.45506 16.7331 4.83379 17.9497 6.05032C19.1662 7.26685 20.5449 7.34795 20.5449 7.34795M16.652 3.45506L10.6872 9.41993C10.2832 9.82394 10.0812 10.0259 9.90743 10.2487C9.70249 10.5114 9.52679 10.7957 9.38344 11.0965C9.26191 11.3515 9.17157 11.6225 8.99089 12.1646L8.41242 13.9M20.5449 7.34795L14.5801 13.3128C14.1761 13.7168 13.9741 13.9188 13.7513 14.0926C13.4886 14.2975 13.2043 14.4732 12.9035 14.6166C12.6485 14.7381 12.3775 14.8284 11.8354 15.0091L10.1 15.5876M10.1 15.5876L8.97709 15.9619C8.71035 16.0508 8.41626 15.9814 8.21744 15.7826C8.01862 15.5837 7.9492 15.2897 8.03811 15.0229L8.41242 13.9M10.1 15.5876L8.41242 13.9"
          stroke="currentColor"
          stroke-width="1.5"
        />
      </svg>
    </div>

    {#if let_me_in || reason}
      <div class="font-medium text-lg">
        {$_("data_generation.intro.synthetic_data_tips")}
      </div>
      <div>
        1. {$_("data_generation.intro.tip_1")}
        <a
          href="https://docs.getkiln.ai/docs/synthetic-data-generation#topic-tree-data-generation"
          target="_blank"
          class="link">{$_("data_generation.intro.guide")}</a
        >.
      </div>
      <div>
        2. {$_("data_generation.intro.tip_2")}
        <a
          href="https://docs.getkiln.ai/docs/synthetic-data-generation#human-guidance"
          target="_blank"
          class="link">{$_("data_generation.intro.guide")}</a
        >.
      </div>
      <button class="btn btn-primary" on:click={() => generate_subtopics()}>
        {$_("data_generation.add_top_level_topics")}
      </button>
      <button class="btn" on:click={() => generate_samples()}>
        {$_("data_generation.add_top_level_data")}
      </button>
      <a
        href="https://docs.getkiln.ai/docs/synthetic-data-generation"
        target="_blank"
        class="btn"
      >
        {$_("data_generation.intro.read_the_docs")}
      </a>
    {:else}
      <div class="font-medium text-lg">
        {$_("data_generation.intro.generate_title")}
      </div>
      <div>
        {$_("data_generation.intro.generate_description")}
      </div>
      <a
        class="btn btn-primary"
        href={`/evals/${project_id}/${task_id}/create_evaluator`}
      >
        {$_("data_generation.intro.create_eval")}
      </a>
      <a
        class="btn btn-primary"
        href={`/fine_tune/${project_id}/${task_id}/create_finetune`}
      >
        {$_("data_generation.intro.create_finetune")}
      </a>
      <button class="btn" on:click={() => (let_me_in = true)}
        >{$_("data_generation.intro.proceed_to_generator")}</button
      >
    {/if}
  </div>
</div>
