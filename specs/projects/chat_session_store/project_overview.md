---
status: complete
---

# Chat Session Store

The `chat.svelte` component currently does 2 things:
- Chat state
- Chat UI

A recent refactor made it so the chat UI can move all over (pane on right, dialog, chat tab). By using chat.svelte 3 times, we end up with 3 unique chat sessions. We want one session, with different views (shared store)

Project:
- refactor the data/storage part of this out into a store. Chat.svelte should be pure UI, and connect to a store. 
- There can be one global primary chat for now, all chats share this. `chat.svelte` should default to using it, unless you pass another store instance.

Tech:
- use svelte stores? Seems ideal
- session storage: if I reload the page I want to keep my chat. If I open a new tab, I expect new chat.
