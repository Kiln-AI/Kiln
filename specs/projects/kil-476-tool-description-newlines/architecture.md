---
status: complete
---

# Architecture: Tool Description Newlines

## Approach

Pure CSS/Tailwind fix. No new components, no data changes, no backend changes.

In HTML, text nodes collapse whitespace by default. The standard way to preserve newlines is `white-space: pre-wrap` (Tailwind: `whitespace-pre-wrap`) which:
- Preserves newlines and spaces
- Still wraps lines at the container boundary (unlike `pre` which doesn't wrap)

`whitespace-pre-line` is an alternative that collapses runs of spaces but preserves newlines. Either works; `whitespace-pre-line` is slightly more forgiving for descriptions that use spaces for indentation.

**Decision: use `whitespace-pre-line`** — consistent with what `fancy_select.svelte` already uses, and more forgiving for descriptions that mix space-indented and newline-separated content.

Also add `break-words` to prevent overflow when a description contains a very long unbroken token (e.g. a URL).

## Changes

### `tool_servers/[tool_server_id]/+page.svelte`

1. **Tool description cell** (line ~585):
   ```svelte
   <!-- before -->
   <td class="max-w-[300px]">{tool.description || "None"}</td>
   
   <!-- after -->
   <td class="max-w-[300px] whitespace-pre-line break-words">{tool.description || "None"}</td>
   ```

2. **Argument description div** (line ~603):
   ```svelte
   <!-- before -->
   <div class="text-gray-500 text-sm mt-1">
     {arg.description}
   </div>
   
   <!-- after -->
   <div class="text-gray-500 text-sm mt-1 whitespace-pre-line break-words">
     {arg.description}
   </div>
   ```

## No Other Files Changed

All other description rendering locations are either already correct or intentionally truncating.
