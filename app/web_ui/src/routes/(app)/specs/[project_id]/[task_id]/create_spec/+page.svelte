<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import { page } from "$app/stores"
  import { formatSpecTypeName } from "$lib/utils/formatters"
  import { onMount } from "svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import { createKilnError, KilnError } from "$lib/utils/error_handlers"
  import type { SpecType } from "$lib/types"
  import { goto } from "$app/navigation"
  import FormElement from "$lib/utils/form_element.svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import { spec_field_configs } from "../select_template/spec_templates"
  import { createSpec, navigateToReviewSpec } from "../spec_utils"

  $: project_id = $page.params.project_id
  $: task_id = $page.params.task_id

  let spec_type: SpecType = "behaviour"
  let name = ""

  // Store property values as a Record<string, string | null>
  let property_values: Record<string, string | null> = {}
  let initial_property_values: Record<string, string | null> = {}
  let initialized = false

  // Get field configs for the current spec_type
  $: field_configs = spec_field_configs[spec_type] || []

  onMount(() => {
    // Check for URL params first (fresh navigation from select_template)
    const spec_type_param = $page.url.searchParams.get("type")
    const has_url_params = spec_type_param !== null

    // Check if we have saved form data from a back navigation
    const formDataKey = `spec_refine_${project_id}_${task_id}`
    const storedData = sessionStorage.getItem(formDataKey)

    if (storedData && !has_url_params) {
      try {
        const formData = JSON.parse(storedData)
        // Restore form state
        spec_type = formData.spec_type || "behaviour"
        name = formData.name || ""
        property_values = { ...formData.property_values }
        initial_property_values = { ...formData.property_values }
        initialized = true
        return
      } catch (error) {
        // If parsing fails, continue with normal initialization
        console.error("Failed to restore form data:", error)
      }
    }

    // If no stored data and no URL params, redirect to specs list
    // This happens when user navigates back after creating a spec
    if (!storedData && !has_url_params) {
      goto(`/specs/${project_id}/${task_id}`)
      return
    }

    // Normal initialization with URL params
    if (spec_type_param) {
      spec_type = spec_type_param as SpecType
    }
    name = formatSpecTypeName(spec_type)

    // Initialize property values from field configs
    // Fields with default_value are pre-filled, others start empty
    const fieldConfigs = spec_field_configs[spec_type] || []
    const values: Record<string, string | null> = {}

    for (const field of fieldConfigs) {
      if (field.default_value !== undefined) {
        values[field.key] = field.default_value
      }
    }

    property_values = values
    initial_property_values = { ...values }

    // Override tool_function_name if provided in URL
    const tool_function_name_param =
      $page.url.searchParams.get("tool_function_name")
    if (tool_function_name_param) {
      property_values["tool_function_name"] = tool_function_name_param
      initial_property_values["tool_function_name"] = tool_function_name_param
    }

    initialized = true
  })

  let create_error: KilnError | null = null
  let submitting = false
  let complete = false
  let warn_before_unload = false

  $: void (name, property_values, initialized, update_warn_before_unload())

  function update_warn_before_unload() {
    if (!initialized) {
      warn_before_unload = false
      return
    }
    if (complete) {
      warn_before_unload = false
      return
    }
    warn_before_unload = has_form_changes()
  }

  let analyze_dialog: Dialog | null = null
  async function analyze_spec() {
    try {
      create_error = null
      submitting = true

      // Validate required fields
      for (const field of field_configs) {
        if (field.required) {
          const value = property_values[field.key]
          if (!value || !value.trim()) {
            throw createKilnError(`${field.label} is required`)
          }
        }
      }

      // Reset submitting state so button doesn't show spinner
      submitting = false

      // Show analyzing dialog
      analyze_dialog?.show()

      // Wait 5 seconds
      await new Promise((resolve) => setTimeout(resolve, 5000))

      // Don't warn before unloading since we're intentionally navigating
      warn_before_unload = false

      // // Navigate to review_spec page
      // await navigateToReviewSpec(
      //   project_id,
      //   task_id,
      //   name,
      //   spec_type,
      //   property_values,
      // )
    } catch (error) {
      create_error = createKilnError(error)
      analyze_dialog?.hide()
      submitting = false
    }
  }

  function reset_field(key: string) {
    property_values[key] = initial_property_values[key] ?? null
  }

  function has_form_changes(): boolean {
    if (!initialized) return false
    if (name !== formatSpecTypeName(spec_type)) return true
    for (const key of Object.keys(property_values)) {
      if (property_values[key] !== initial_property_values[key]) return true
    }
    return false
  }

  async function create_spec() {
    try {
      create_error = null
      submitting = true
      complete = false

      // Validate required fields
      for (const field of field_configs) {
        if (field.required) {
          const value = property_values[field.key]
          if (!value || !value.trim()) {
            throw createKilnError(`${field.label} is required`)
          }
        }
      }

      const spec_id = await createSpec(
        project_id,
        task_id,
        name,
        spec_type,
        property_values,
      )

      if (spec_id) {
        complete = true
        goto(`/specs/${project_id}/${task_id}/${spec_id}`)
      }
    } catch (error) {
      create_error = createKilnError(error)
    } finally {
      submitting = false
    }
  }
</script>

<div class="max-w-[900px]">
  <AppPage
    title="Define Spec"
    subtitle={`Template: ${formatSpecTypeName(spec_type)}`}
    breadcrumbs={[
      {
        label: "Specs",
        href: `/specs/${project_id}/${task_id}`,
      },
      {
        label: "Spec Templates",
        href: `/specs/${project_id}/${task_id}/select_template`,
      },
    ]}
  >
    <FormContainer
      submit_label="Next"
      on:submit={analyze_spec}
      bind:error={create_error}
      bind:submitting
      {warn_before_unload}
    >
      <FormElement
        label="Spec Name"
        description="A short name for your own reference."
        id="spec_name"
        bind:value={name}
      />

      {#each field_configs as field (field.key)}
        <FormElement
          label={field.label}
          id={field.key}
          inputType="textarea"
          disabled={field.disabled || false}
          description={field.description}
          height={field.height || "base"}
          bind:value={property_values[field.key]}
          optional={!field.required}
          inline_action={initial_property_values[field.key]
            ? {
                handler: () => reset_field(field.key),
                label: "Reset",
              }
            : undefined}
        />
      {/each}
    </FormContainer>
    <div class="flex flex-row gap-1 mt-2 justify-end">
      <span class="text-xs text-gray-500">or</span>
      <button
        class="link underline text-xs text-gray-500"
        on:click={create_spec}>Create Spec Without Analysis</button
      >
    </div>
  </AppPage>
</div>

<Dialog
  bind:this={analyze_dialog}
  title="Analyzing Spec"
  sub_subtitle="Generating data for you to review next to refine your spec"
>
  <div class="flex flex-col items-center justify-center min-h-[100px]">
    <svg
      width="500"
      height="500"
      viewBox="0 0 500 500"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <defs>
        <clipPath id="canvas-clip">
          <rect width="500" height="500" />
        </clipPath>
      </defs>
      <rect width="500" height="500" fill="white" />
      <g clip-path="url(#canvas-clip)">
        <!--
      ╔══════════════════════════════════════════════════════════════════════════════╗
      ║                         ANIMATION TIMELINE DOCUMENTATION                     ║
      ╚══════════════════════════════════════════════════════════════════════════════╝
      
      OVERVIEW:
      This animation shows 8 boxes appearing, with 3 fading out and 5 remaining.
      The remaining 5 boxes then move simultaneously to new positions, followed by
      checkmarks and X icons appearing on them.
      
      TIMELINE STRUCTURE:
      ────────────────────────────────────────────────────────────────────────────────
      
      PHASE 1: STAGGERED APPEARANCE (0.1s - 1.45s)
        • All 8 boxes appear at staggered times with scale animations
        • Each box: scale animation (0.3s duration) + opacity fade in (0.1s)
        • Box appearance times (top to bottom, 0.15s intervals):
          - Box 1: 0.10s
          - Box 2: 0.25s (will fade out)
          - Box 3: 0.40s (will fade out)
          - Box 4: 0.55s
          - Box 5: 0.70s (will fade out)
          - Box 6: 0.85s
          - Box 7: 1.00s
          - Box 8: 1.15s (finishes at 1.45s with 0.3s animation)
      
      PHASE 2: SYNCHRONIZED FADE OUT (2.0s - 3.0s)
        • Three boxes (Box 2, Box 3, Box 5) fade out simultaneously
        • All three START fading at 2.0s and END at 3.0s
        • Critical: All appearances complete before fading begins
        • Box 2: fades 2.0s → 3.0s (1.0s duration)
        • Box 3: fades 2.0s → 3.0s (1.0s duration)
        • Box 5: fades 2.0s → 3.0s (1.0s duration)
      
      PHASE 3: SYNCHRONIZED MOVEMENT (3.0s - 4.0s)
        • All 5 remaining boxes move to their final positions IN SYNC
        • Start time: 3.0s (immediately after fade-out completes)
        • Duration: 1.0s (all boxes move together)
        • End time: 4.0s (all movements complete simultaneously)
        • Movements:
          - Box 1: y=24  → y=83  (moves down 59px)
          - Box 4: y=198 → y=155 (moves up 43px)
          - Box 6: y=314 → y=227 (moves up 87px)
          - Box 7: y=372 → y=299 (moves up 73px)
          - Box 8: y=430 → y=371 (moves up 59px)
      
      PHASE 4: ICONS APPEAR (4.2s - 5.0s)
        • Checkmarks and X icons appear on the final boxes
        • Start time: 4.2s (0.2s buffer after movement completes)
        • Staggered appearance times (0.2s intervals):
          - Checkmark 1 (Box 1): 4.2s
          - Checkmark 2 (Box 4): 4.4s
          - Checkmark 3 (Box 6): 4.6s
          - X icon 1 (Box 7):    4.8s
          - X icon 2 (Box 8):    5.0s
      
      PHASE 5: FLY OUT TO RIGHT (6.0s - 7.0s)
        • After 1.0s hold, all boxes and icons fly out to the right
        • Start time: 6.0s (1.0s hold after last icon appears at 5.0s)
        • Duration: 0.6s per row
        • Staggered by 0.1s (top to bottom):
          - Row 1 (Box 1 + Check 1): 6.0s - 6.6s
          - Row 2 (Box 4 + Check 2): 6.1s - 6.7s
          - Row 3 (Box 6 + Check 3): 6.2s - 6.8s
          - Row 4 (Box 7 + X 1):     6.3s - 6.9s
          - Row 5 (Box 8 + X 2):     6.4s - 7.0s
        • All elements move from current x position to x=600 (off-screen right)
      
      KEY TIMING DECISIONS:
      ────────────────────────────────────────────────────────────────────────────────
      1. Fade-out phase is isolated: No movement occurs during fade completion
      2. All fade-outs synchronized to end at exactly 3.0s
      3. Movement phase is synchronized: All boxes move together (3.0s - 4.0s)
      4. Movement duration is exactly 1.0s for clean, crisp animation
      5. Icons appear only after movement completes (0.2s buffer for clarity)
      6. Icon appearances are staggered for visual interest (0.2s intervals)
      7. Fly-out starts after 1.0s hold (at 6.0s) with top-to-bottom stagger (0.1s)
      
      MODIFICATION GUIDELINES:
      ────────────────────────────────────────────────────────────────────────────────
      • To change fade-out timing: Adjust fade durations so all end at same time
      • To change movement timing: Update all 5 boxes' y-animate begin/dur together
      • To adjust movement speed: Modify dur="1s" on all movement animations
      • To shift icon timing: Ensure icons start after movement phase completes
      • To change fly-out timing: Adjust both box x-animate and icon translate together
      • To adjust stagger interval: Modify 0.1s increments between row fly-outs
      • Phase boundaries: 0s → 3.0s → 4.0s → 5.0s → 6.0s → 7.0s
      -->

        <!-- FADING BOXES (render behind) -->
        <!-- Box 2: y=82 (fades out) -->
        <rect
          id="box2"
          x="89"
          y="82"
          width="322"
          height="45"
          rx="10"
          stroke="#415CF5"
          stroke-width="2"
          opacity="0"
          transform-origin="250 104.5"
        >
          <animateTransform
            attributeName="transform"
            type="scale"
            values="1; 1; 1.3; 1; 1; 1"
            keyTimes="0; 0.0357; 0.0579; 0.0786; 0.429; 1"
            begin="0s"
            dur="7s"
            repeatCount="indefinite"
          />
          <animate
            attributeName="opacity"
            values="0; 0; 1; 1; 0; 0"
            keyTimes="0; 0.0357; 0.05; 0.2857; 0.4286; 1"
            begin="0s"
            dur="7s"
            repeatCount="indefinite"
          />
        </rect>

        <!-- Box 3: y=140 (fades out) -->
        <rect
          id="box3"
          x="89"
          y="140"
          width="322"
          height="45"
          rx="10"
          stroke="#415CF5"
          stroke-width="2"
          opacity="0"
          transform-origin="250 162.5"
        >
          <animateTransform
            attributeName="transform"
            type="scale"
            values="1; 1; 1.3; 1; 1; 1"
            keyTimes="0; 0.0571; 0.0793; 0.1; 0.429; 1"
            begin="0s"
            dur="7s"
            repeatCount="indefinite"
          />
          <animate
            attributeName="opacity"
            values="0; 0; 1; 1; 0; 0"
            keyTimes="0; 0.0571; 0.0714; 0.2857; 0.4286; 1"
            begin="0s"
            dur="7s"
            repeatCount="indefinite"
          />
        </rect>

        <!-- Box 5: y=256 (fades out) -->
        <rect
          id="box5"
          x="89"
          y="256"
          width="322"
          height="45"
          rx="10"
          stroke="#415CF5"
          stroke-width="2"
          opacity="0"
          transform-origin="250 278.5"
        >
          <animateTransform
            attributeName="transform"
            type="scale"
            values="1; 1; 1.3; 1; 1; 1"
            keyTimes="0; 0.1; 0.1221; 0.1429; 0.429; 1"
            begin="0s"
            dur="7s"
            repeatCount="indefinite"
          />
          <animate
            attributeName="opacity"
            values="0; 0; 1; 1; 0; 0"
            keyTimes="0; 0.1; 0.1143; 0.2857; 0.4286; 1"
            begin="0s"
            dur="7s"
            repeatCount="indefinite"
          />
        </rect>

        <!-- STAYING BOXES (render on top) -->
        <!-- Box 1: y=24 -> y=83 (stays, moves, gets checkmark) -->
        <rect
          id="box1"
          x="89"
          y="24"
          width="322"
          height="45"
          rx="10"
          stroke="#415CF5"
          stroke-width="2"
          opacity="0"
          transform-origin="250 46.5"
        >
          <animateTransform
            attributeName="transform"
            type="scale"
            values="1; 1; 1.3; 1; 1; 1"
            keyTimes="0; 0.0143; 0.0364; 0.0571; 0.857; 1"
            begin="0s"
            dur="7s"
            repeatCount="indefinite"
          />
          <animate
            attributeName="opacity"
            values="0; 0; 1; 1; 1; 0; 0"
            keyTimes="0; 0.0143; 0.0286; 0.857; 0.943; 0.944; 1"
            begin="0s"
            dur="7s"
            repeatCount="indefinite"
          />
          <animate
            attributeName="y"
            values="24; 24; 83; 83; 24"
            keyTimes="0; 0.429; 0.571; 0.999; 1"
            begin="0s"
            dur="7s"
            repeatCount="indefinite"
          />
          <animate
            attributeName="x"
            values="89; 89; 600; 89"
            keyTimes="0; 0.857; 0.943; 1"
            begin="0s"
            dur="7s"
            repeatCount="indefinite"
          />
        </rect>

        <!-- Box 4: y=198 -> y=155 (stays, moves, gets checkmark) -->
        <rect
          id="box4"
          x="89"
          y="198"
          width="322"
          height="45"
          rx="10"
          stroke="#415CF5"
          stroke-width="2"
          opacity="0"
          transform-origin="250 220.5"
        >
          <animateTransform
            attributeName="transform"
            type="scale"
            values="1; 1; 1.3; 1; 1; 1"
            keyTimes="0; 0.0786; 0.1007; 0.1214; 0.857; 1"
            begin="0s"
            dur="7s"
            repeatCount="indefinite"
          />
          <animate
            attributeName="opacity"
            values="0; 0; 1; 1; 1; 0; 0"
            keyTimes="0; 0.0786; 0.0929; 0.871; 0.957; 0.958; 1"
            begin="0s"
            dur="7s"
            repeatCount="indefinite"
          />
          <animate
            attributeName="y"
            values="198; 198; 155; 155; 198"
            keyTimes="0; 0.429; 0.571; 0.999; 1"
            begin="0s"
            dur="7s"
            repeatCount="indefinite"
          />
          <animate
            attributeName="x"
            values="89; 89; 600; 89"
            keyTimes="0; 0.871; 0.957; 1"
            begin="0s"
            dur="7s"
            repeatCount="indefinite"
          />
        </rect>

        <!-- Box 6: y=314 -> y=227 (stays, moves, gets checkmark) -->
        <rect
          id="box6"
          x="89"
          y="314"
          width="322"
          height="45"
          rx="10"
          stroke="#415CF5"
          stroke-width="2"
          opacity="0"
          transform-origin="250 336.5"
        >
          <animateTransform
            attributeName="transform"
            type="scale"
            values="1; 1; 1.3; 1; 1; 1"
            keyTimes="0; 0.1214; 0.1436; 0.1643; 0.857; 1"
            begin="0s"
            dur="7s"
            repeatCount="indefinite"
          />
          <animate
            attributeName="opacity"
            values="0; 0; 1; 1; 1; 0; 0"
            keyTimes="0; 0.1214; 0.1357; 0.886; 0.971; 0.972; 1"
            begin="0s"
            dur="7s"
            repeatCount="indefinite"
          />
          <animate
            attributeName="y"
            values="314; 314; 227; 227; 314"
            keyTimes="0; 0.429; 0.571; 0.999; 1"
            begin="0s"
            dur="7s"
            repeatCount="indefinite"
          />
          <animate
            attributeName="x"
            values="89; 89; 600; 89"
            keyTimes="0; 0.886; 0.971; 1"
            begin="0s"
            dur="7s"
            repeatCount="indefinite"
          />
        </rect>

        <!-- Box 7: y=372 -> y=299 (stays, moves, gets X) -->
        <rect
          id="box7"
          x="89"
          y="372"
          width="322"
          height="45"
          rx="10"
          stroke="#415CF5"
          stroke-width="2"
          opacity="0"
          transform-origin="250 394.5"
        >
          <animateTransform
            attributeName="transform"
            type="scale"
            values="1; 1; 1.3; 1; 1; 1"
            keyTimes="0; 0.1429; 0.165; 0.1857; 0.857; 1"
            begin="0s"
            dur="7s"
            repeatCount="indefinite"
          />
          <animate
            attributeName="opacity"
            values="0; 0; 1; 1; 1; 0; 0"
            keyTimes="0; 0.1429; 0.1571; 0.9; 0.986; 0.987; 1"
            begin="0s"
            dur="7s"
            repeatCount="indefinite"
          />
          <animate
            attributeName="y"
            values="372; 372; 299; 299; 372"
            keyTimes="0; 0.429; 0.571; 0.999; 1"
            begin="0s"
            dur="7s"
            repeatCount="indefinite"
          />
          <animate
            attributeName="x"
            values="89; 89; 600; 89"
            keyTimes="0; 0.9; 0.986; 1"
            begin="0s"
            dur="7s"
            repeatCount="indefinite"
          />
        </rect>

        <!-- Box 8: y=430 -> y=371 (stays, moves, gets X) -->
        <rect
          id="box8"
          x="89"
          y="430"
          width="322"
          height="45"
          rx="10"
          stroke="#415CF5"
          stroke-width="2"
          opacity="0"
          transform-origin="250 452.5"
        >
          <animateTransform
            attributeName="transform"
            type="scale"
            values="1; 1; 1.3; 1; 1; 1"
            keyTimes="0; 0.1643; 0.1864; 0.2071; 0.857; 1"
            begin="0s"
            dur="7s"
            repeatCount="indefinite"
          />
          <animate
            attributeName="opacity"
            values="0; 0; 1; 1; 1; 0; 0"
            keyTimes="0; 0.1643; 0.1786; 0.914; 0.999; 0.9991; 1"
            begin="0s"
            dur="7s"
            repeatCount="indefinite"
          />
          <animate
            attributeName="y"
            values="430; 430; 371; 371; 430"
            keyTimes="0; 0.429; 0.571; 0.999; 1"
            begin="0s"
            dur="7s"
            repeatCount="indefinite"
          />
          <animate
            attributeName="x"
            values="89; 89; 600; 89"
            keyTimes="0; 0.914; 0.999; 1"
            begin="0s"
            dur="7s"
            repeatCount="indefinite"
          />
        </rect>

        <!-- Checkmark 1 (for box at y=83) -->
        <g id="check1" opacity="0" transform-origin="379 105.8">
          <g transform="scale(0.5) translate(379, 105.8)">
            <path
              fill-rule="evenodd"
              clip-rule="evenodd"
              d="M370.515 104.766C369.254 103.478 367.208 103.478 365.946 104.766C364.685 106.055 364.685 108.145 365.946 109.434L372.408 116.034C373.67 117.322 375.715 117.322 376.977 116.034L392.054 100.634C393.315 99.3447 393.315 97.2553 392.054 95.9666C390.792 94.6778 388.746 94.6778 387.485 95.9666L374.692 109.033L370.515 104.766Z"
              fill="#415CF5"
            />
          </g>
          <animateTransform
            attributeName="transform"
            type="scale"
            values="1; 1; 1.3; 1; 1; 1"
            keyTimes="0; 0.6; 0.621; 0.643; 0.857; 1"
            begin="0s"
            dur="7s"
            repeatCount="indefinite"
          />
          <animate
            attributeName="opacity"
            values="0; 0; 1; 1; 1; 0; 0"
            keyTimes="0; 0.6; 0.614; 0.857; 0.943; 0.944; 1"
            begin="0s"
            dur="7s"
            repeatCount="indefinite"
          />
          <animateTransform
            attributeName="transform"
            type="translate"
            values="0,0; 0,0; 511,0; 0,0"
            keyTimes="0; 0.857; 0.943; 1"
            begin="0s"
            dur="7s"
            repeatCount="indefinite"
            additive="sum"
          />
        </g>

        <!-- Checkmark 2 (for box at y=155) -->
        <g id="check2" opacity="0" transform-origin="379 177.8">
          <g transform="scale(0.5) translate(379, 177.8)">
            <path
              fill-rule="evenodd"
              clip-rule="evenodd"
              d="M370.515 176.766C369.254 175.478 367.208 175.478 365.946 176.766C364.685 178.055 364.685 180.145 365.946 181.434L372.408 188.034C373.67 189.322 375.715 189.322 376.977 188.034L392.054 172.634C393.315 171.345 393.315 169.255 392.054 167.967C390.792 166.678 388.746 166.678 387.485 167.967L374.692 181.033L370.515 176.766Z"
              fill="#415CF5"
            />
          </g>
          <animateTransform
            attributeName="transform"
            type="scale"
            values="1; 1; 1.3; 1; 1; 1"
            keyTimes="0; 0.629; 0.650; 0.671; 0.871; 1"
            begin="0s"
            dur="7s"
            repeatCount="indefinite"
          />
          <animate
            attributeName="opacity"
            values="0; 0; 1; 1; 1; 0; 0"
            keyTimes="0; 0.629; 0.643; 0.871; 0.957; 0.958; 1"
            begin="0s"
            dur="7s"
            repeatCount="indefinite"
          />
          <animateTransform
            attributeName="transform"
            type="translate"
            values="0,0; 0,0; 511,0; 0,0"
            keyTimes="0; 0.871; 0.957; 1"
            begin="0s"
            dur="7s"
            repeatCount="indefinite"
            additive="sum"
          />
        </g>

        <!-- Checkmark 3 (for box at y=227) -->
        <g id="check3" opacity="0" transform-origin="379 249.8">
          <g transform="scale(0.5) translate(379, 249.8)">
            <path
              fill-rule="evenodd"
              clip-rule="evenodd"
              d="M370.515 248.766C369.254 247.478 367.208 247.478 365.946 248.766C364.685 250.055 364.685 252.145 365.946 253.434L372.408 260.034C373.67 261.322 375.715 261.322 376.977 260.034L392.054 244.634C393.315 243.345 393.315 241.255 392.054 239.967C390.792 238.678 388.746 238.678 387.485 239.967L374.692 253.033L370.515 248.766Z"
              fill="#415CF5"
            />
          </g>
          <animateTransform
            attributeName="transform"
            type="scale"
            values="1; 1; 1.3; 1; 1; 1"
            keyTimes="0; 0.657; 0.679; 0.7; 0.886; 1"
            begin="0s"
            dur="7s"
            repeatCount="indefinite"
          />
          <animate
            attributeName="opacity"
            values="0; 0; 1; 1; 1; 0; 0"
            keyTimes="0; 0.657; 0.671; 0.886; 0.971; 0.972; 1"
            begin="0s"
            dur="7s"
            repeatCount="indefinite"
          />
          <animateTransform
            attributeName="transform"
            type="translate"
            values="0,0; 0,0; 511,0; 0,0"
            keyTimes="0; 0.886; 0.971; 1"
            begin="0s"
            dur="7s"
            repeatCount="indefinite"
            additive="sum"
          />
        </g>

        <!-- X 1 (for box at y=299) -->
        <g id="x1" opacity="0" transform-origin="379 322">
          <g transform="scale(0.5) translate(379, 322)">
            <path
              d="M382.503 322L389.263 328.722C390.246 329.7 390.246 331.167 389.263 332.144C388.894 332.633 388.279 333 387.665 333C387.05 333 386.436 332.756 385.944 332.267L379.061 325.422L372.302 332.144C371.318 333.122 369.721 333.122 368.86 332.144C368.369 331.778 368 331.167 368 330.433C368 329.7 368.246 329.211 368.737 328.722L375.497 322L368.737 315.278C368.369 314.789 368 314.178 368 313.444C368 312.833 368.246 312.222 368.737 311.733C369.229 311.244 369.844 311 370.458 311C371.073 311 371.687 311.244 372.179 311.733L378.939 318.456L385.698 311.733C386.682 310.756 388.279 310.756 389.14 311.733C390.123 312.711 390.123 314.3 389.14 315.156L382.503 322Z"
              fill="#415CF5"
            />
          </g>
          <animateTransform
            attributeName="transform"
            type="scale"
            values="1; 1; 1.3; 1; 1; 1"
            keyTimes="0; 0.686; 0.707; 0.729; 0.9; 1"
            begin="0s"
            dur="7s"
            repeatCount="indefinite"
          />
          <animate
            attributeName="opacity"
            values="0; 0; 1; 1; 1; 0; 0"
            keyTimes="0; 0.686; 0.7; 0.9; 0.986; 0.987; 1"
            begin="0s"
            dur="7s"
            repeatCount="indefinite"
          />
          <animateTransform
            attributeName="transform"
            type="translate"
            values="0,0; 0,0; 511,0; 0,0"
            keyTimes="0; 0.9; 0.986; 1"
            begin="0s"
            dur="7s"
            repeatCount="indefinite"
            additive="sum"
          />
        </g>

        <!-- X 2 (for box at y=371) -->
        <g id="x2" opacity="0" transform-origin="379 394">
          <g transform="scale(0.5) translate(379, 394)">
            <path
              d="M375.497 394L368.737 387.278C367.754 386.3 367.754 384.833 368.737 383.856C369.106 383.367 369.721 383 370.335 383C370.95 383 371.564 383.244 372.056 383.733L378.939 390.578L385.698 383.856C386.682 382.878 388.279 382.878 389.14 383.856C389.631 384.222 390 384.833 390 385.567C390 386.3 389.754 386.789 389.263 387.278L382.503 394L389.263 400.722C389.631 401.211 390 401.822 390 402.556C390 403.167 389.754 403.778 389.263 404.267C388.771 404.756 388.156 405 387.542 405C386.927 405 386.313 404.756 385.821 404.267L379.061 397.544L372.302 404.267C371.318 405.244 369.721 405.244 368.86 404.267C367.877 403.289 367.877 401.7 368.86 400.844L375.497 394Z"
              fill="#415CF5"
            />
          </g>
          <animateTransform
            attributeName="transform"
            type="scale"
            values="1; 1; 1.3; 1; 1; 1"
            keyTimes="0; 0.714; 0.736; 0.757; 0.914; 1"
            begin="0s"
            dur="7s"
            repeatCount="indefinite"
          />
          <animate
            attributeName="opacity"
            values="0; 0; 1; 1; 1; 0; 0"
            keyTimes="0; 0.714; 0.729; 0.914; 0.999; 0.9991; 1"
            begin="0s"
            dur="7s"
            repeatCount="indefinite"
          />
          <animateTransform
            attributeName="transform"
            type="translate"
            values="0,0; 0,0; 511,0; 0,0"
            keyTimes="0; 0.914; 0.999; 1"
            begin="0s"
            dur="7s"
            repeatCount="indefinite"
            additive="sum"
          />
        </g>
      </g>
    </svg>
  </div>
</Dialog>
