---
name: establish_intent
description: |
  Classify the user's intent and route to the right mode.
---
# Mode: Establish Intent

Determine what the user wants to accomplish and route them to the appropriate mode.

## Goal

Understand the user's intent and get them into the right mode as quickly as possible.

## Route Before Discovery

When the user's intent is clear enough to identify the destination mode, **load that mode file immediately** — before calling any APIs, including project/task discovery. Task Context Discovery is defined inside each mode and runs after the mode is loaded. **Never call `call_kiln_api` from Establish Intent** — discovery happens inside the destination mode, not here.

## Routing reference

This file is the deep-load target on a real intent change — re-anchor here when re-routing. The canonical routing summary (Quick-Jump, Suggested Questions, Mode Routing table, What Kiln Assistant Can Help With) is always in context via SKILL.md → Establish Intent. Read that section as the authoritative source for every routing rule.
