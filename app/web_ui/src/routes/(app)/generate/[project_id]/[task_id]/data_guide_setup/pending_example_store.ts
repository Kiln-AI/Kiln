import { writable } from "svelte/store"
import type { GuideSample } from "./guide_setup_form.svelte"

// One-shot handoff store: the synth page sets a pending example here when
// the user adds it from the data-guide intro dialog, then navigates to
// /data_guide_setup. The setup page reads it on mount and clears it. Memory
// only — a hard refresh between navigation drops the seed (acceptable since
// the user can re-trigger from the synth intro).
export const pending_data_guide_example = writable<GuideSample | null>(null)
