# Phase 7: References & Assets — Frontend

## Goal

Add file upload and management UI for skill references and assets on both the create page and the detail/edit page. Depends on Phase 6 backend endpoints being in place.

## Files to Modify

### Modify: `app/web_ui/src/routes/(app)/settings/manage_skills/[project_id]/create/+page.svelte`

Add reference and asset upload sections to the create form:

**References section** (below the body textarea):

- "References" label with info tooltip explaining what references are
- List of added references with filename + content preview + delete button
- "Add Reference" button → opens a dialog/inline form for filename + markdown content textarea
- References are submitted alongside the skill create request (multi-step API call: create skill first, then save references)

**Assets section** (below references):

- "Assets" label with info tooltip explaining what assets are for
- File upload area (drag-and-drop zone, reuse pattern from `upload_file_dialog.svelte` in docs library)
- List of uploaded assets with filename + size + delete button
- Assets are uploaded after skill creation (POST to the asset upload endpoint)

**Create flow**:

1. User fills in name, description, body, adds references and assets
2. On submit: POST create skill → save_skill_md → save each reference → upload each asset
3. On success: navigate to skill detail page

### Modify: `app/web_ui/src/routes/(app)/settings/manage_skills/[project_id]/[skill_id]/+page.svelte`

Add reference and asset management to the detail/edit page:

**References section**:

- List of existing references loaded via `GET .../references`
- Click a reference to view/edit its content (inline or in a dialog)
- "Add Reference" button
- Delete button per reference
- Empty state: "No references. Add reference documentation to give agents more context."

**Assets section**:

- List of existing assets loaded via `GET .../assets`
- Upload button (drag-and-drop zone)
- Delete button per asset
- Show filename, file size, file type
- Empty state: "No assets. Upload files like schemas, templates, or images."

### Modify: `app/web_ui/src/lib/types.ts`

After regenerating the API schema, ensure the new file management endpoints are typed.

## Testing

1. **Create page**: References and assets can be added before submission, submitted correctly via multi-step flow
2. **Detail page**: References and assets load from API, can be added/edited/deleted
3. **File upload**: Drag-and-drop works, file type validation, error handling
4. **Empty states**: Appropriate messages when no references or assets exist
5. **Error handling**: Network errors, invalid filenames, upload failures

## Key Design Notes

- The create flow is multi-step (create skill → add files) since the skill directory must exist before files can be written. The UI should handle this seamlessly — the user fills everything in at once and the submit handler orchestrates the API calls.
- Reuse the drag-and-drop upload pattern from `upload_file_dialog.svelte` in the docs library
- References are text-based (primarily markdown) — use a textarea for content, not file upload
- Assets are binary files — use file upload with drag-and-drop
- Consider a file preview for markdown references (rendered) and asset metadata display (size, type)
