---
status: complete
---

# Collapsible Sidebar

We’ve added a chat pane on the right of our main layout `(app)/layout.svelte`. We always had a 

This project: collapse the left nav to an icon rail when needed.

Design:
- Tooltips on hover to show the names. position - coming out the right, centred on icon. Should be near instant appear.
- Optimize group: separate with horizontal lines and small “OPTIMIZE” title in top. No longer nested to right, but use this division.
- Task selector: reduce down to a single letter representation in a box “Joke Generator” task becomes “J”. Keep with chevron. Hover shows 2 line tooltip with project/name

Condition:
- only collapse if chat bar is open and screen width < 1550px. Otherwise keep current design. 
- Can’t manually toggle, except to close chat which will bring it back