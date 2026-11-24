<script lang="ts">
  // A grounded case's judge guidance and the reset arguments it ran with,
  // read-only: the guidance is what the judge graded against.
  import Collapse from "$lib/ui/collapse.svelte"
  import SettingsHeader from "$lib/ui/settings_header.svelte"
  import PropertyList from "$lib/ui/property_list.svelte"
  import type { UiProperty } from "$lib/ui/property_list"
  import Output from "$lib/ui/output.svelte"
  import ChatMarkdown from "$lib/ui/chat/chat_markdown.svelte"
  import type { OpenEnvReset } from "$lib/types"
  import { flatten_reset_arguments } from "./grounding_flow"

  export let openenv_reset: OpenEnvReset | null = null
  export let judge_guidance: string

  // Values longer than a short line (setup scripts, long descriptions) render
  // in a folded Output so one argument can't push the guidance off screen.
  const LONG_VALUE_CHARS = 80
  // Output measures its fold in pixels.
  const LONG_VALUE_MAX_HEIGHT = "120px"
  const GUIDANCE_MAX_HEIGHT = "320px"

  function is_long(value: string): boolean {
    return value.length > LONG_VALUE_CHARS || value.includes("\n")
  }

  let properties: UiProperty[]
  $: properties = flatten_reset_arguments(openenv_reset?.reset_kwargs).map(
    (row) => ({
      name: row.path,
      value: row.value,
      use_custom_slot: is_long(row.value),
    }),
  )
</script>

<!-- The judge guidance is open: it is what the judge graded this case against,
     and its starting point already says where the case begins. The exact reset
     arguments stay folded under Environment Options, for when the reviewer
     wants to check them. -->
<div class="flex flex-col gap-3" data-environment-guidance>
  <SettingsHeader
    title="Judge Guidance"
    subtitle="What the judge checks this case against: where it starts, what Kiln found in the environment, and the expected outcome."
    show_divider={false}
  />
  <Output raw_output={judge_guidance} max_height={GUIDANCE_MAX_HEIGHT}>
    <ChatMarkdown text={judge_guidance} />
  </Output>
  <Collapse title="Environment Options" outlined>
    {#if properties.length > 0}
      <PropertyList {properties}>
        <svelte:fragment slot="custom_value" let:property>
          <div class="w-full min-w-0">
            <Output
              raw_output={String(property.value)}
              max_height={LONG_VALUE_MAX_HEIGHT}
            />
          </div>
        </svelte:fragment>
      </PropertyList>
    {:else}
      <div class="text-sm text-gray-500">
        Starts from the server's default state.
      </div>
    {/if}
  </Collapse>
</div>
