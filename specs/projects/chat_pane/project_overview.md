---
status: complete
---

# Chat Pane — Project Overview

We’re building a chat sidebar and chat page for this app.

Scope:

- this is a small project just around layout. We should be working essentially only in `(app)/layout.svelte` and `chat_bar.svelte`. You can create new files if needed, but we don’t want to start editing `chat.svelte`. The chat.svelte is owned by another developer, and I’m trying to keep this PR clean/separate.

**Status**
I’ve got some basic stuff started, but want you to take it over. Run `git diff 2140c9803ea53d52652e0f30fcd9615f03e58c33
 HEAD` to see the initial work.

Spec:

- The app is going to have a “chat” feature. You can access it either on the /chat page (full screen), or via a sidebar on the right.
- When on `/chat` screen, the chat bar disappears. It would be redundant. Current implementation here: `{section ==  Section.Chat  ? 'hidden'  : ''}`
- Expand/Hide: at a screen size you can hit an X in the chat bar, and it collapses to a small chat icon in bottom right of layout (floating).
  - Clicking the icon brings back the chat bar. The icon only isn’t visible on the chat page.
  - The user’s preferred state (expanded/collapsed) should be saved to local storage and session storage. On fresh reload we restore the state: prefer session storage over local storage if set, so the window keeps its behaviour, but on new windows you get “last decision” via local storage. Make a new `chat_ui_storage.ts` helper for this.
- Bar behaviour per screen size:
  - below the tailwind “lg:” selector the chat bar is a Dialog that opens full screen (see dialog.svelte). This screen size is too small for side-by-side bar. This still allows them to use chat anywhere, without leaving current screen, so good UX.
  - “lg:” and larger, it’s a bar beside the main content (partly implemented). On “2xl” size it gets a size boost as screen is bigger.
- Later stage enhancement 1: custom size
  - make the a separate later implementation phase, I want the rest working cleanly before we add this.
  - The user should be able to drag to resize the side-bar version by dragging an indicator (cursor helper for discovery).
  - The preferred size should be saved in local storage across sessions, with new sessions getting the last saved width. This impact future windows, not other windows I currently have open. Last in wins.

Note: the way `chat.svelte` works each instance will have its own state. Another project we’ll enhance this so the many instances share. This is not in scope for this project, which is focused on UX/UI of the pane.
