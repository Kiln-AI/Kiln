<script lang="ts">
  import { createEventDispatcher } from "svelte"
  import StarIcon from "$lib/ui/icons/star_icon.svelte"
  import OptimizeIcon from "$lib/ui/icons/optimize_icon.svelte"
  import ArrowUpIcon from "$lib/ui/icons/arrow_up_icon.svelte"
  import EvalIcon from "$lib/ui/icons/eval_icon.svelte"
  const dispatch = createEventDispatcher<{ select: string }>()

  const primarySuggestions = [
    {
      icon: StarIcon,
      title: "Improve quality",
      subtitle: "Better outputs from my task",
      prompt: "Help me improve the quality of my task outputs",
    },
    {
      icon: OptimizeIcon,
      title: "Cut costs",
      subtitle: "Cheaper models or fine-tuning",
      prompt: "Help me reduce costs for running my task",
    },
    {
      icon: ArrowUpIcon,
      title: "Speed it up",
      subtitle: "Lower latency, faster runs",
      prompt: "Help me make my task faster with lower latency",
    },
    {
      icon: EvalIcon,
      title: "Build an eval",
      subtitle: "Measure what matters",
      prompt: "Help me create an eval to measure and improve my AI system",
    },
  ]

  const secondarySuggestions = [
    {
      label: "Run on-prem",
      prompt: "Help me run this task on-prem or with a local model",
    },
    {
      label: "Synthetic data",
      prompt: "Help me generate synthetic training data for my task",
    },
    {
      label: "Fine-tune",
      prompt: "Help me fine-tune a model for my use case",
    },
  ]
</script>

<div class="welcome-container w-full">
  <div class="max-w-lg mx-auto px-4 py-12">
    <!-- Header -->
    <div class="text-center mb-10">
      <img
        src="/images/chat_icon.svg"
        alt="Kiln"
        class="w-24 h-14 mx-auto mb-4"
      />
      <h1 class="text-xl font-medium mb-2">What are you optimizing?</h1>
      <p class="welcome-subtitle text-sm text-gray-500 font-light">
        I know your tasks, evals, and data. Tell me what to improve.
      </p>
    </div>

    <!-- Primary suggestions -->
    <div class="welcome-grid-primary grid gap-2 mb-2">
      {#each primarySuggestions as suggestion}
        <button
          class="flex items-start gap-2.5 px-4 py-3.5 rounded-xl border border-base-300 bg-base-100 text-left transition-colors hover:border-gray-400 hover:bg-base-200"
          on:click={() => dispatch("select", suggestion.prompt)}
        >
          <div class="w-4 h-4 mt-0.5 flex-shrink-0 text-gray-500">
            <svelte:component this={suggestion.icon} />
          </div>
          <div>
            <span class="text-sm font-medium block">{suggestion.title}</span>
            <span class="welcome-subtitle text-xs text-gray-500 mt-0.5">
              {suggestion.subtitle}
            </span>
          </div>
        </button>
      {/each}
    </div>

    <!-- Secondary suggestions -->
    <div class="welcome-grid-secondary gap-2 mb-2">
      {#each secondarySuggestions as suggestion}
        <button
          class="text-center px-2 py-2.5 rounded-xl border border-base-300 bg-base-100 text-sm text-gray-500 transition-colors hover:border-gray-400 hover:bg-base-200 hover:text-base-content"
          on:click={() => dispatch("select", suggestion.prompt)}
        >
          {suggestion.label}
        </button>
      {/each}
    </div>

    <!-- Footer -->
    <p class="text-center text-gray-400">
      Or just ask — I can work with any task in your project.
    </p>
  </div>
</div>

<style>
  .welcome-container {
    container-type: inline-size;
  }

  .welcome-grid-primary {
    grid-template-columns: 1fr;
  }

  .welcome-grid-secondary {
    display: none;
  }

  .welcome-subtitle {
    display: none;
  }

  @container (min-width: 380px) {
    .welcome-grid-primary {
      grid-template-columns: 1fr 1fr;
    }

    .welcome-grid-secondary {
      display: grid;
      grid-template-columns: 1fr 1fr 1fr;
    }

    .welcome-subtitle {
      display: block;
    }
  }
</style>
