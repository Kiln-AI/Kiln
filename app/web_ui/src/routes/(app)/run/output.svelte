<script lang="ts">
  import hljs from "highlight.js/lib/core"
  import json from "highlight.js/lib/languages/json"
  hljs.registerLanguage("json", json)

  export let raw_output: string
  let formatted_json_html: string | null = null
  $: {
    try {
      const json_output = JSON.parse(raw_output)
      // Strings are JSON, but not really
      if (typeof json_output !== "string") {
        formatted_json_html = JSON.stringify(json_output, null, 2)
        formatted_json_html = hljs.highlight(formatted_json_html, {
          language: "json",
        }).value
      }
    } catch (e) {
      formatted_json_html = null
    }
  }

  function copy_to_clipboard() {
    navigator.clipboard.writeText(raw_output)
  }
</script>

<head>
  <link rel="stylesheet" href="/styles/highlightjs.min.css" />
</head>

<div class="flex flex-row gap-2 bg-base-200 p-1 rounded-lg">
  <!-- eslint-disable svelte/no-at-html-tags -->
  <pre
    class="grow p-3 whitespace-pre-wrap text-xs min-w-0"
    style="overflow-wrap: anywhere;">{#if formatted_json_html}{@html formatted_json_html}{:else}{raw_output}{/if}</pre>
  <!-- eslint-enable svelte/no-at-html-tags -->
  <div class="flex-none">
    <button
      on:click={copy_to_clipboard}
      class="btn btn-sm btn-square h-8 w-8 shadow-none text-gray-400 hover:text-gray-900"
    >
      <!-- Uploaded to: SVG Repo, www.svgrepo.com, Generator: SVG Repo Mixer Tools -->
      <svg
        class="w-5 h-5 p-0"
        viewBox="0 0 64 64"
        xmlns="http://www.w3.org/2000/svg"
        stroke-width="3"
        stroke="currentColor"
        fill="none"
      >
        <rect x="11.13" y="17.72" width="33.92" height="36.85" rx="2.5" />
        <path
          d="M19.35,14.23V13.09a3.51,3.51,0,0,1,3.33-3.66H49.54a3.51,3.51,0,0,1,3.33,3.66V42.62a3.51,3.51,0,0,1-3.33,3.66H48.39"
        />
      </svg>
    </button>
  </div>
</div>
