# Sample queries at each level of the guide

A sub-file of [guide skill for a tool set](references/improving_agents/techniques/guide-skill-for-a-tool-set.md).
Read it when you write a guide for a general query tool: SQL, GraphQL, or a
general API that takes a query. It says which sample queries to put in the
guide, at which level, and how to write them.

## Why samples come first

A schema lists what exists. It does not show how the tool is used: which
table answers a common question, which filter is always needed, which join
is safe. A sample query shows all of that in a few lines. An agent that
reads a sample close to its question can change the sample, and it does not
have to build the query from the schema.

Samples do not replace the schema. The schema stays in leaf files, for the
complex query that no sample covers. See
[the schema as leaf files](references/improving_agents/techniques/guide-skill-for-a-tool-set/schema-as-leaf-files.md).

## Where each sample goes

The guide has levels. Each level has its own samples.

1. **The `SKILL.md` body.** A few samples of the most common kinds of
   question. Each one is short. Together they show the main tables or
   types, the filters that most queries need, and the conventions (how a
   status is written, how a date range is written, how many rows to ask
   for). An agent that reads only the body can write the common query.
2. **The leaf file of each area.** An area is a group of tables or types
   that queries use together, for example orders and their lines. Its
   file starts with samples for that area, from the simple to the complex:
   - one filter on one table;
   - a count or a sum, with a group;
   - a join of two tables, on the right keys;
   - a time range (see [timestamps](references/improving_agents/techniques/guide-skill-for-a-tool-set/timestamps.md));
   - the top or the latest few rows;
   - a comparison of two periods, or of two groups.
   Then the file gives the schema of the area.
3. **The schema leaf files.** A sample next to each join or field that is
   a trap: the join that duplicates rows, the field with codes, the field
   that is empty on old rows.

Put a sample at the level where the agent looks for it. A sample for one
area in the body costs tokens on every question of every other area.

## What each sample holds

- **The question in a user's words.** Write it as a user would ask it, with
  the words that a question would use. The agent finds a sample by these
  words.
- **The query**, complete, in the form that the tool takes.
- **One line on the result**: what one row means, and the unit of each
  number.
- **The trap, if there is one**, as a comment next to the line that
  avoids it.

An example of the form, with invented names and values:

```
Question: How many orders were shipped last week?
Query:
  SELECT count(*) AS shipped_orders
  FROM orders
  WHERE status = 'shipped'        -- stored in lower case
    AND shipped_at >= :week_start
    AND shipped_at <  :next_week_start   -- end bound is exclusive
Result: one row, one number of orders.
```

## How to choose the samples

- **From the kinds of question in the traces**, not from the tables. Name
  the kinds of question that the traces show (what is asked, not the words
  or the values of one item), and write one sample for each common kind,
  with invented values (the leak rules of
  `references/knowledge/train_val_test.md`). A table that no question uses
  needs no sample.
- **From the shape of queries that worked**, in the traces or in the
  product's own documentation. Keep the shape of a query that returned
  the right result, and replace each of its values with an invented one
  or a parameter.
- **Show how to ask for less.** Include a limit on rows, a count or a sum
  in place of raw rows, and only the columns that the answer needs. A
  sample is copied, so its habits are copied too.
- **Not every query.** When one query appears on most items, a fixed tool
  can be better than a sample: see [roll-up tool](references/improving_agents/techniques/roll-up-tool.md).

## Rules for each sample

- **Never from a train item.** Do not copy a question, a value or an
  answer from a train item or from an eval. Invent the values. A sample
  that holds a train value teaches the agent that value, and the
  measurement then measures the copy.
- **Run each sample once** before it goes in the guide, as a read, and
  check that it returns what its line says. A wrong sample can be worse
  than no sample, because the agent copies it.
- **Keep the samples in step with the tool.** A skill is immutable. When
  the schema or the tool changes, the samples change in a new version of
  the skill.
- **Use parameters for dates and ids** (`:week_start`), not fixed values,
  so that the agent sees which part to change.
- **A sample does not hold a guard.** A limit that the product needs (no
  write, a cap on rows) goes in a wrapper, not in a sample. See
  [cap and preview wrapper](references/improving_agents/techniques/cap-and-preview-wrapper.md) and
  [guard tool calls at the boundary](references/improving_agents/techniques/guard-tool-calls-at-the-boundary.md).

## How to check the samples

Run the candidate on two or three train items that need the query tool. In
each trace, find the read of the body or of an area file, then a query that
has the shape of a sample. When the agent reads the file and writes a query
of another shape, the samples do not match its questions.
