---
status: complete
---

# Ask User Question (suggested-answers prompt)

A new flow/tool that lets the assistant **ask the user a question and offer up to 5 suggested
answers**, instead of only free-form prose. Each suggested answer has a **main answer line** plus a
**1–2 line explanation**. There is **always** a **"Chat about this"** option so the user can refine
the question through chatting — when chosen, the model asks them, in an open way, what they want.

Built on the same machinery as auto-mode: a client-visible backend tool the app server intercepts
and surfaces to the browser, which renders the question + options and posts back the user's choice
to resolve the tool call.

## Locked decisions (kickoff)

- **"Chat about this"** → the tool resolves with a "wants to chat" signal; the model then responds
  with an **open follow-up question** ("what would you like to adjust / tell me more about…?") and
  the user free-types.
- **Input while a question is pending** → the normal text input is **blocked**; the user must pick
  a suggested answer or "Chat about this" (which then enables typing).
- **Selecting a suggested answer** → **one-click send**: the answer's main line becomes the user's
  response (the explanation is context only).
- **In auto-mode** → the question is **surfaced and the burst pauses (goes idle, flag stays on)**;
  answering (pick or chat) continues the work in auto-mode. Composes with auto-mode Revision R1.

## Branch / PR

- New branch `leonard/ask-user-question` off `leonard/kil-692-assistant-auto-mode`; PR targets
  `leonard/kil-692-assistant-auto-mode`.
