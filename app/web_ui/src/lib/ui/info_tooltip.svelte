<script lang="ts">
  export let tooltip_text: string
</script>

<button class="tooltip tooltip-left" data-tip={tooltip_text}>
  <svg
    fill="currentColor"
    class="w-6 h-6 inline"
    viewBox="0 0 1024 1024"
    version="1"
    xmlns="http://www.w3.org/2000/svg"
    ><path
      d="M512 717a205 205 0 1 0 0-410 205 205 0 0 0 0 410zm0 51a256 256 0 1 1 0-512 256 256 0 0 1 0 512z"
    /><path
      d="M485 364c7-7 16-11 27-11s20 4 27 11c8 8 11 17 11 28 0 10-3 19-11 27-7 7-16 11-27 11s-20-4-27-11c-8-8-11-17-11-27 0-11 3-20 11-28zM479 469h66v192h-66z"
    /></svg
  >
</button>
