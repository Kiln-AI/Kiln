---
status: draft
---

# Agentic Eval

A new eval type: a better "LLM as judge" for large traces.

## The Problem

The trace we're asked to evaluate might be 600k tokens. It might even be 5M tokens that went through several compaction windows. Inserting the whole trace into the judge's context might not be possible, or might just be a bad idea.

Many of those tokens are useless to a given judge:

- **"Did it call the right tools?" judge:** doesn't need to see 500k tokens of tool responses. It probably doesn't need assistant messages or thinking either. User messages and tool call signatures are enough.
- **"Did it end the conversation properly?" judge:** can read the last few assistant messages. It doesn't need the rest.
- etc.

There are infinite use cases like these.

## The Goal

A multi-turn, agentic eval:

- **Judge prompt.** Just like the LLM-as-judge prompt. But the template probably doesn't inject the full trace (`{{ trace }}`) into the prompt. It could optionally include a summary (first user message, turn count, tool call count), or use Jinja to craft a summary that makes sense for this specific judge.
- **Trace-reading tools.** Unlike LLM as judge, the agentic judge gets a set of tools for reading the trace. These need to be designed, and they must be token efficient. Rough ideas:
  - Give me all user messages
  - Give me all assistant messages
  - Give me all user messages, assistant messages and tool calls (but not tool responses)
  - Give me the last 4 assistant messages
  - Give me tool response N
  - Give me the first 300 chars of every message
  - Show me a summary of the trace, e.g. `1: user [453 chars], 2: assistant [1234 chars], 3: tool_call [tool_x, response chars: 3645], 4: tool_call ...`

  A powerful set of tools that lets the judge explore the whole trace without loading the whole thing into context.
- **Advanced tool options:**
  - Search/grep the trace: search for a pattern and return (1) the location and (2) N surrounding chars.
  - Truncate long messages by default, with an overridable `max_chars`, so the judge can get the full message when it needs it, without dumping 5k tokens into context unintentionally.
  - TBD if more.

The agentic judge should be smart: loading what it needs, in steps, and ignoring irrelevant parts (e.g. a 50k-token tool response that isn't salient to the eval). It can work progressively.
