import type { components } from "$lib/api_schema"
import type { Option } from "$lib/ui/fancy_select_types"
import { GOLDEN_TARGET } from "./claim_evidence"

type SplitShare = components["schemas"]["SplitShare"]

export type BatchProfileKey = "standard" | "deep" | "smoke_test" | "custom"

export type BatchSize = { profile: BatchProfileKey; custom_count: number }

export const CUSTOM_MIN = 35
export const CUSTOM_MAX = 120

export const DEFAULT_BATCH_SIZE: BatchSize = {
  profile: "standard",
  custom_count: 60,
}

const EVEN_THREE_WAY: SplitShare[] = [
  { split: "test", weight: 1 },
  { split: "train", weight: 1 },
  { split: "val", weight: 1 },
]

type BatchProfile = {
  key: BatchProfileKey
  label: string
  badge?: string
  description: string
  dealt: number | null
  shares: SplitShare[]
}

// The product's sizes and copy.
export const BATCH_PROFILES: BatchProfile[] = [
  {
    key: "standard",
    label: "Standard",
    badge: "Recommended",
    description: "60 items across train, val, test.",
    dealt: 60,
    shares: EVEN_THREE_WAY,
  },
  {
    key: "deep",
    label: "Deep",
    description: "120 items across train, val, test.",
    dealt: 120,
    shares: EVEN_THREE_WAY,
  },
  {
    key: "smoke_test",
    label: "Smoke Test",
    description:
      "20 items, all in the test set. Can't be used for auto-optimize.",
    dealt: 20,
    shares: [{ split: "test", weight: 1 }],
  },
  {
    key: "custom",
    label: "Custom",
    description: "Set your own item count.",
    dealt: null,
    shares: EVEN_THREE_WAY,
  },
]

function profile_for(key: BatchProfileKey): BatchProfile {
  return BATCH_PROFILES.find((p) => p.key === key) ?? BATCH_PROFILES[0]
}

function clamp_custom_count(count: number): number {
  return Math.min(CUSTOM_MAX, Math.max(CUSTOM_MIN, count))
}

function dealt_count(size: BatchSize): number {
  return (
    profile_for(size.profile).dealt ?? clamp_custom_count(size.custom_count)
  )
}

export function planned_count(size: BatchSize): number {
  return dealt_count(size) + GOLDEN_TARGET
}

export function shares_for(size: BatchSize): SplitShare[] {
  return profile_for(size.profile).shares
}

export function restore_batch_size(
  saved: BatchSize | null | undefined,
): BatchSize {
  if (!saved || !BATCH_PROFILES.some((p) => p.key === saved.profile)) {
    return { ...DEFAULT_BATCH_SIZE }
  }
  return {
    profile: saved.profile,
    custom_count: clamp_custom_count(saved.custom_count),
  }
}

export function profile_options(): Option[] {
  return BATCH_PROFILES.map((profile) => ({
    label: profile.label,
    value: profile.key,
    description: profile.description,
    ...(profile.badge
      ? { badge: profile.badge, badge_color: "primary" as const }
      : {}),
  }))
}
