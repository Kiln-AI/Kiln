<script lang="ts">
  // Generic no-op stub used to replace child components in run_config_component
  // tests so the parent's reactive logic can be tested in isolation without the
  // children performing their own data loading.
  export function get_selected_model(): string | null {
    return null
  }
</script>
