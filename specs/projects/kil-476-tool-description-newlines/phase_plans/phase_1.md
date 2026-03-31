---
status: complete
---

# Phase 1: Add Whitespace Preservation to Tool Description Elements

## Overview

Adds `whitespace-pre-line break-words` Tailwind classes to the two description-rendering elements in the tool server detail page so that multi-line MCP tool and argument descriptions render with proper line breaks instead of collapsing into a single flat string.

## Steps

1. **Edit `app/web_ui/src/routes/(app)/tools/[project_id]/tool_servers/[tool_server_id]/+page.svelte` line 585** — tool description `<td>`:
   - Before: `<td class="max-w-[300px]">{tool.description || "None"}</td>`
   - After: `<td class="max-w-[300px] whitespace-pre-line break-words">{tool.description || "None"}</td>`

2. **Edit same file line 603** — argument description `<div>`:
   - Before: `<div class="text-gray-500 text-sm mt-1">`
   - After: `<div class="text-gray-500 text-sm mt-1 whitespace-pre-line break-words">`

## Tests

No unit tests are required — this is a pure CSS/Tailwind class change. Visual verification confirms:
- Newlines in tool descriptions render as line breaks
- Long unbroken tokens wrap within the column (no overflow)
- Missing descriptions still display "None"
