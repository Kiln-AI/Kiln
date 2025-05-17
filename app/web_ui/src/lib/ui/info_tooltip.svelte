<script lang="ts">
  export let tooltip_text: string
  export let position: "left" | "right" | "bottom" | "top" = "left"
  export let no_pad = false

  function get_position_class() {
    switch (position) {
      case "right":
        return "tooltip-right"
      case "bottom":
        return "tooltip-bottom"
      case "top":
        return "tooltip-top"
      default:
        return "tooltip-left"
    }
  }
</script>

<button
  class="tooltip before:z-50 {get_position_class()} before:whitespace-normal"
  data-tip={tooltip_text}
>
  <svg
    fill="currentColor"
    class="w-6 h-6 inline {no_pad ? 'mt-[-3px] ml-[-3px]' : ''}"
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
