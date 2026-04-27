---
status: complete
---

# Phase 3: Settings page "Update Available" header

## Overview

When the rail is active and an app update is available, the dedicated "App Update Available" list item is replaced by a dot badge on the Settings icon (shipped in Phase 2). Clicking Settings routes to `/settings` — so the settings page itself needs to provide the affordance the removed rail pill used to.

This phase prepends an **"Update Available"** callout to `/settings` whenever `$update_info.update_result?.has_update` is true.

The rendering is a page-level concern — it does not depend on whether the rail is active. It's equally useful for a desktop user viewing `/settings` from the full sidebar: an inline reminder + CTA to check for the update.

## Design decision (UI signoff, supersedes original plan)

The original plan below prescribed reusing `KilnSection` + `SettingsItem` primitives so the update affordance matched the visual rhythm of the rest of the page. During UI signoff the user explicitly rejected that approach: rendered as a `KilnSection`, the update item looked like just another settings section and failed to grab attention.

**Final design:** a compact blue-tinted callout card rendered above the sections (outside the `sections` array), built inline in the `+page.svelte` template. It uses `card card-bordered border-primary/30 bg-primary/5`, a circular primary-tinted icon (`ArrowUpIcon`), a short title ("Update Available"), a one-line description, and a primary button linking to `/settings/check_for_update`. The `sections` array is unchanged.

This note supersedes the `KilnSection`-based sample in the Steps section below. Keep the existing "Check for Update" item in Help & Resources regardless.

## Steps

1. **Modify `app/web_ui/src/routes/(app)/settings/+page.svelte`**:
    - Import `update_info` from `$lib/utils/update`.
    - Make `sections` reactive (`$:`) so it recomputes when `$update_info` changes.
    - Prepend an "Update Available" `KilnSection` when `$update_info.update_result?.has_update` is true:
      ```ts
      $: sections = [
        ...($update_info.update_result?.has_update
          ? [
              {
                category: "Update Available",
                items: [
                  {
                    type: "settings",
                    name: "New version available",
                    description:
                      "A new version of Kiln is ready to install.",
                    button_text: "View Update",
                    href: "/settings/check_for_update",
                  } as KilnSectionItem,
                ],
              },
            ]
          : []),
        // ...existing sections unchanged
      ]
      ```
    - Keep the existing "Check for Update" item in Help & Resources (lets users force a check even when `has_update` is false).

## Tests

- `app/web_ui/src/routes/(app)/settings/page.test.ts`
  - Renders "Update Available" section at the top when `update_info.update_result.has_update` is true.
  - Renders the "View Update" button linking to `/settings/check_for_update`.
  - Does NOT render the "Update Available" section when `has_update` is false (`default_update_state`).
  - Does NOT render the section when `update_result` is null.
  - "Update Available" section appears before "Current Workspace" when shown (ordering).
  - The "Check for Update" item in Help & Resources is still present regardless of update state.
