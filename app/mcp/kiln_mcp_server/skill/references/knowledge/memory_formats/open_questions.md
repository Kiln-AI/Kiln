---
name: open_questions
description: Read-only - the format of the OPEN records, the open questions that Kiln Harness Tuner's code writes as constraint records - the overview, the five content lines and how to read them.
---

# Open questions

Kiln Harness Tuner's code writes an open question as a `constraint`
record with the overview prefix `OPEN: `, and reads it back to find a
question it has already asked. Its code is the authority on the format. It
is here so that you can read it. Never write or edit an `OPEN: ` record
(`references/knowledge/memory.md`).

## The overview

`OPEN: <question>`. Example: `OPEN: unknown if the graphql endpoint has docs`.

## The content

Five `key: value` lines, in this order:

```
question: <the question, on one line>
default: <the default assumed until it is answered>
gates: <what the answer decides>
source: assumption
re-ask when: <when to ask again>
```

`source:` is `assumption` when code writes it, and `human` once a person
confirms it. Its code finds a question it already asked by the
`question:` line.

## How to read it

- Read the `OPEN: ` records before you ask the user anything: never ask
  what is already answered.
- An answered question has no prefix: a person removed it and added the
  answer, its source and the date.
- An experiment stamped ` — HELD (constraint <id>) <MM-DD>` waits on the
  `OPEN: ` record `<id>`
  (`references/knowledge/memory_formats/experiment_records.md`).
