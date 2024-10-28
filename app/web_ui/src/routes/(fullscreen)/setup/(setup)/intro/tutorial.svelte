<script lang="ts">
  import TutorialSection from "./tutorial_section.svelte"
  import { fly } from "svelte/transition"
  let section = 0

  let sections = [
    {
      title: "Data Driven Improvements",
      promos: [
        "As you use your models, Kiln automatically creates a rich dataset.",
        "Prompts improve themselves, using past results and ratings.",
        "Handle structured input and output with ease.",
      ],
      image_path: "/images/data_driven.png",
    },
    {
      title: "Collaborate with Your Team",
      promos: [
        "Our data format is designed for Git. Work with your team, with tools you know.",
        "Our easy-to-use app makes it easy for non-technical team members to contribute.",
        "Completely private: we don't see your dataset, period.",
      ],
      image_path: "/images/collaborate.png",
    },
    {
      title: "Find the best way to run your task",
      promos: [
        "Try over a dozen different foundation models.",
        "Bring your own keys, or run locally with Ollama.",
        "Optimize performance and costs for your task.",
      ],
      image_path: "/images/logo_grid.png",
    },
    {
      title: "Library and API",
      promos: [
        "Our open-source python library makes it easy to extend Kiln.",
        "Use our REST API to integrate Kiln with your own applications.",
      ],
      image_path: "/images/developers.png",
    },
  ]

  export let completed: boolean = false
  $: completed = section === sections.length - 1

  let prior_section = section
  function set_section(new_section: number) {
    prior_section = section
    section = Math.max(0, Math.min(sections.length - 1, new_section))
  }

  function handleKeydown(event: KeyboardEvent) {
    if (event.key === "ArrowLeft") {
      set_section(section - 1)
    } else if (event.key === "ArrowRight") {
      set_section(section + 1)
    }
  }
</script>

<svelte:window on:keydown={handleKeydown} />

<div class="grow"></div>
<div class="flex flex-col md:flex-row gap-12 place-items-center">
  <button
    class="size-10 text-gray-300 {section === 0 ? 'opacity-0' : ''}"
    on:click={() => set_section(section - 1)}
  >
    <!-- Uploaded to: SVG Repo, www.svgrepo.com, Generator: SVG Repo Mixer Tools -->
    <svg
      fill="currentColor"
      class="size-10"
      version="1.1"
      id="Layer_1"
      xmlns="http://www.w3.org/2000/svg"
      xmlns:xlink="http://www.w3.org/1999/xlink"
      viewBox="0 0 493.468 493.468"
      xml:space="preserve"
    >
      <g>
        <g>
          <path
            d="M246.736,0C110.688,0,0.008,110.692,0.008,246.732c0,136.056,110.68,246.736,246.728,246.736
			S493.46,382.788,493.46,246.732C493.46,110.692,382.784,0,246.736,0z M197.592,249.536l94.764,94.776
			c1.012,1.004,1.568,2.348,1.568,3.776c0,1.448-0.556,2.784-1.568,3.772l-8.96,8.98c-2.004,2.004-5.568,2.012-7.568,0
			l-110.14-110.136c-1.008-1.016-1.556-2.38-1.54-3.932c-0.016-1.476,0.532-2.828,1.536-3.852l110.312-110.304
			c1.004-1.004,2.34-1.56,3.776-1.56c1.424,0,2.788,0.556,3.78,1.56l8.968,8.98c2.1,2.06,2.1,5.468,0.004,7.548l-94.932,94.944
			C196.084,245.592,196.084,248.024,197.592,249.536z"
          />
        </g>
      </g>
    </svg>
  </button>
  <div class="md:w-[650px] md:h-[400px]">
    {#key section}
      <div
        id="tutorial_section_{section}"
        in:fly={{ x: prior_section < section ? 100 : -100 }}
      >
        <TutorialSection
          title={sections[section].title}
          promos={sections[section].promos}
          image_path={sections[section].image_path}
        />
      </div>
    {/key}
  </div>
  <button
    class="size-10 text-primary {section === sections.length - 1
      ? 'opacity-0'
      : ''}"
    on:click={() => set_section(section + 1)}
  >
    <!-- Uploaded to: SVG Repo, www.svgrepo.com, Generator: SVG Repo Mixer Tools -->
    <svg
      fill="currentColor"
      class="size-10"
      version="1.1"
      id="Layer_1"
      xmlns="http://www.w3.org/2000/svg"
      xmlns:xlink="http://www.w3.org/1999/xlink"
      viewBox="0 0 493.456 493.456"
      xml:space="preserve"
    >
      <g>
        <g>
          <path
            d="M246.73,0C110.682,0,0.002,110.68,0.002,246.736c0,136.036,110.68,246.72,246.728,246.72s246.724-110.684,246.724-246.72
   C493.454,110.68,382.778,0,246.73,0z M321.138,250.492L210.822,360.804c-2.004,2.008-5.548,2.008-7.556,0l-8.98-8.968
   c-2.076-2.084-2.072-5.48,0.004-7.564l94.952-94.94c0.712-0.72,1.116-1.7,1.116-2.732c0-1.016-0.408-2.004-1.116-2.72
   l-94.78-94.776c-1-1-1.56-2.344-1.56-3.792c0-1.42,0.556-2.772,1.556-3.764l8.968-8.976c1.004-1,2.352-1.556,3.78-1.556
   c1.436-0.008,2.772,0.556,3.776,1.556l110.156,110.152c1.02,1.016,1.572,2.372,1.552,3.936
   C322.71,248.116,322.158,249.476,321.138,250.492z"
          />
        </g>
      </g>
    </svg>
  </button>
</div>
<div class="grow-[1.5]"></div>
