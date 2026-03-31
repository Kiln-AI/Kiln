---
status: complete
---

# Functional Spec: Tool Description Newlines

## Problem

MCP tools sourced from external servers often have multi-line descriptions — e.g.:

```
Search the web for information.

Use this tool when you need up-to-date facts, current events, or
information that may have changed recently.

Returns a list of results with titles and snippets.
```

The current UI renders this as a flat string, collapsing all whitespace. The result is unreadable for any description longer than one line.

## Affected Locations

### 1. Tool Server Detail Page — Tool Descriptions

**File:** `app/web_ui/src/routes/(app)/tools/[project_id]/tool_servers/[tool_server_id]/+page.svelte`

The "Available Tools" table renders each tool's description in a `<td>` with no whitespace handling:

```svelte
<td class="max-w-[300px]">{tool.description || "None"}</td>
```

**Fix:** Add `whitespace-pre-wrap` (or `whitespace-pre-line`) so newlines render. Keep `max-w-[300px]` to prevent the column getting too wide. Use `break-words` to prevent overflow on very long unbroken lines.

### 2. Tool Server Detail Page — Argument Descriptions

**File:** same file as above

Each tool's argument list also shows descriptions without whitespace handling:

```svelte
<div class="text-gray-500 text-sm mt-1">
  {arg.description}
</div>
```

**Fix:** Same treatment — add `whitespace-pre-wrap` and `break-words`.

## Out of Scope

- **Tools overview page** (`tools/[project_id]/+page.svelte`): The description column there shows user-entered tool server descriptions (e.g. "My company's internal tools"), not MCP descriptions. These are unlikely to contain newlines and the column is narrow. Leave as-is.
- **Kiln task tools list** (`kiln_task_tools/+page.svelte`): Uses `truncate` by design — it's a compact summary table. Leave as-is.
- **Fancy select dropdown**: Already has `whitespace-pre-line`. No change needed.

## Behavior

- Newlines in tool/argument descriptions render as actual line breaks.
- Long unbroken text wraps within the column (no horizontal overflow).
- Empty/null descriptions continue to show "None" as before.
- No layout changes needed — multi-line descriptions naturally expand the row height, which is correct behavior for a detail page.
