---
status: complete
---

# Assistant Auto-Mode

We want to implement an **auto-mode** in the Kiln assistant. When auto-mode is enabled, the
assistant can autonomously kick off jobs and run tool calls (via the Kiln API Call Tool tool
calls) without stopping to ask the user to approve each step.

The idea we are starting with:

- Add a new tool like **"enable auto mode"**.
- Our backend (the external Kiln Copilot service that this app server passes the chat messages
  on to) can ask whether to trigger auto-mode — it does not always make sense to enable it. We
  should **also** allow the user to enable it directly in the UI.

When auto-mode is on, it is only on for **this one chat session**. It should live **in memory
only, but server-side**. The user may close the web UI altogether, and we should continue doing
the work on the app server.

If the user comes back, we should merge the list of **History → Chat History → N conversations**
with the conversation currently ongoing somehow (probably separating the list, or adding a green
dot showing it is doing work). If the user loads it, we should be able to hydrate the conversation
correctly using the **latest trace from the server**, and wire the stream back up, so on.

Auto-mode should only continue for this **one chat conversation**, until it stops. When it stops
doing whatever it does while in auto — when it asks the user for input, or thinks it is done — it
should be **disabled again**.

Triggering auto-mode should **ask the user if they want to enable it** and explain the
implications, and allow the user to accept or not. It should explain that it uses tokens and may
trigger costly jobs and so on (for reflective optimization). We should then also have a **UI
indicator** showing when it is in auto mode — probably something like "⏵⏵ auto mode on" under the
message input area, maybe in green.

## Key Decisions (from kickoff)

- **Project scope:** New repo-root project (`assistant_auto_mode`). Auto-mode is infrastructure;
  reflective optimization is a use case that rides on it later.
- **Execution model:** A **separate in-memory chat session runner**, server-side and decoupled
  from the browser's HTTP request, with its own registry + SSE stream (modeled on, but distinct
  from, the existing background-job system). This is required because today the agent loop
  (`ChatStreamSession.stream()`) is tied to the browser's `/api/chat` request and dies when the
  UI closes.
- **Auto-approval:** When auto-mode is ON, **all** tool calls auto-execute, including those that
  normally require user approval. The upfront consent prompt covers the blanket risk.
- **Trigger:** Both — the backend can call an `enable_auto_mode` tool (app server intercepts and
  prompts for consent), and the user can toggle it from the chat UI (same consent explanation).
