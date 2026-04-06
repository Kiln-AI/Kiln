---
status: draft
---

# Phase 6: Cross-linking + Clone

## Overview

This phase adds cross-linking between DocSkill and Skill detail pages, and the Clone action on the DocSkill detail page. The DocSkill detail page already links to the generated Skill. This phase adds: (1) a Clone button on the DocSkill detail page that navigates to the creation form with pre-filled values, (2) a "Created from Documents" banner on the Skill detail page that links back to the source DocSkill.

## Steps

1. **Add Clone button to DocSkill detail page** (`app/web_ui/src/routes/(app)/docs/doc_skills/[project_id]/[doc_skill_id]/doc_skill/+page.svelte`):
   - Add a "Clone" action button alongside the existing Archive button in the `action_buttons` array
   - Clone navigates to `/docs/doc_skills/${project_id}/create_doc_skill?clone=${doc_skill_id}`
   - Only show Clone when doc_skill is loaded and not in error state

2. **Add DocSkill source banner to Skill detail page** (`app/web_ui/src/routes/(app)/skills/[project_id]/[skill_id]/+page.svelte`):
   - On mount, call `GET /api/projects/{project_id}/skills/{skill_id}/doc_skill_source`
   - If response has `doc_skill_id`, show a subtle info banner at the top of main content: "Created from Documents" with doc skill name as a link
   - Use neutral/info styling, not prominent
   - Link navigates to `/docs/doc_skills/${project_id}/${doc_skill_id}/doc_skill`

3. **Verify clone flow end-to-end**: The creation form already has `load_clone_source` that fetches the source DocSkill and pre-fills fields. The `+page.svelte` already reads the `clone` URL param. Verify this works correctly with the new Clone button.

## Tests

- Skill detail page: test that doc_skill_source banner renders when source exists
- Skill detail page: test that banner does not render when no source
- DocSkill detail page: test that Clone button exists and has correct href
