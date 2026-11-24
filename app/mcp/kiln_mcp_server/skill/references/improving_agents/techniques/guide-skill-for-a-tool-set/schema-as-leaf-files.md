# The schema as leaf files

A sub-file of [guide skill for a tool set](references/improving_agents/techniques/guide-skill-for-a-tool-set.md).
Read it when you write a guide for a general query tool and the schema does
not fit in the body, or when the traces show queries that fail on names,
joins or codes. It says where the schema goes in the guide and what each
leaf file holds.

## Where the schema goes

- **Not in the body.** The body is a map: for each kind of question, which
  area file to read. It names each area and its key terms. It does not list
  the tables.
- **One leaf file for each area.** An area is a group of tables or types
  that queries use together. The file starts with a contents line that
  names what it holds, with its key terms, then the samples of the area
  (see [sample queries](references/improving_agents/techniques/guide-skill-for-a-tool-set/sample-queries.md)), then the schema.
- **One more level only when an area is too large.** Split it by sub-area.
  Each extra level is one more read before the query, so keep the tree
  shallow.
- **Views first.** When the data has curated views or a semantic layer
  (named measures, dimensions and joins), describe those, and describe the
  raw tables only where no view covers a question. A view holds the joins
  and the filters that a raw query must find again each time.

## What a leaf file holds

For each table or type that the area uses:

- **What one row is** (the grain): one order, one order line, one event.
  A query that mixes grains counts wrong.
- **Each field that queries use**:
  - its name, exactly as the tool takes it;
  - what it means, in plain words;
  - its type and its unit (an amount in cents or in units, net or gross);
  - for a code or a status, each value and its meaning;
  - for a field with a small set of values, the values as they are stored,
    so that the agent writes the stored value and does not guess a form;
  - what an empty value means, and whether old rows have it;
  - for a date or a time, its time zone and format (see
    [timestamps](references/improving_agents/techniques/guide-skill-for-a-tool-set/timestamps.md)).
- **The joins**: the keys on each side, and the traps. A join from a parent
  to its children repeats the parent on each child, so a sum over the
  parent counts it more than once.
- **The fields to leave out**: ids that no question uses, fields kept for
  history, fields that look right and are not (an old status field next
  to the current one).

Fields that no question uses do not need a line. A shorter file is read
faster, and the agent has fewer wrong names to choose.

## A glossary

Put the business terms in one place, in the body or in its own leaf file:
what "active customer", "revenue" or "a return" means as a filter or a
measure on the schema. A user asks in these terms, and the right filter is
often not plain from the field names.

## For GraphQL

- Each type, field, argument and enum that queries use, with what it means.
- Which fields are lists, and how a list is paged.
- The cost or depth limits of the server, when it has them.
- Mutations in their own file, apart from the queries, with what each one
  changes.

## Where the schema comes from

- **From the tool and the system**: an introspection query or a schema
  read, run as a read, and the product's own documentation.
- **From the traces**: the fields that queries used, and the errors that
  named a field that does not exist.
- **Never from a train item or an eval.** No value of an item goes into
  the guide.
- **Mark what is not known.** When a field's meaning is not plain from
  the source, say so. A guessed meaning in the guide is copied into every
  query.

## Rules that go with the leaf files

- **Keep the files in step with the schema.** A skill is immutable. A
  schema change needs a new version of the skill.
- **The guide does not hold a guard.** It can say that a query must have a
  limit. A limit that must hold goes in a wrapper: see
  [cap and preview wrapper](references/improving_agents/techniques/cap-and-preview-wrapper.md).
- **When the schema is too large for a skill**, keep the tool that looks up
  the schema, and let the guide name its areas and their key terms, so
  that the agent knows what to look up.

## How to check the leaf files

Smoke two or three train items that need a complex query. In each trace,
find the read of the right area file before the query, and no error on a
name that does not exist. When the agent reads the wrong area file, the
contents line or the body's map does not name the key terms of the
question.
