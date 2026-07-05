<script lang="ts">
  import FileIcon from "./file_icon.svelte"
</script>

<!-- Prop-less document icon so it can be used where a bare icon component is
expected (e.g. OptionList's `icon`). Wraps FileIcon's "document" variant. -->
<FileIcon kind="document" />
