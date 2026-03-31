---
status: complete
---

# KIL-476: Tool Descriptions Should Show Newlines

MCP tool descriptions and argument descriptions frequently contain newlines (e.g. multi-paragraph descriptions, bulleted instructions). These are currently rendered as collapsed plain text in the UI — all whitespace is ignored — making long or structured descriptions unreadable.

The fix is to preserve whitespace/newlines when rendering tool descriptions and argument descriptions in the relevant UI locations.
