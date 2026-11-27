# Timestamps

A sub-file of [guide skill for a tool set](references/improving_agents/techniques/guide-skill-for-a-tool-set.md).
Read it when you write a guide for a query tool over data that has a date
or a time field. Dates and times are a frequent trap, because a query with
the wrong time zone or the wrong bound returns a plausible number that is
wrong. The guide gets a section on them. This file says what that section
holds.

## For each date or time field

State, in the leaf file of its area (see
[the schema as leaf files](references/improving_agents/techniques/guide-skill-for-a-tool-set/schema-as-leaf-files.md)):

- **What it records**: the time of the event, the time of creation, the
  time of the last change, or the time that the row was loaded. Two
  fields with similar names can record different things.
- **Its type**: a date only, or a date and a time.
- **Its time zone**: UTC, the time zone of the user, of the account, or of
  the place of the event. Say which one, for each field.
- **Its format**, when the tool takes or returns text: for example
  `YYYY-MM-DD`, or a full timestamp with its offset.

## "Today" and relative periods

- **The agent does not know the date** unless something gives it. The
  guide says where the current date comes from: the input, a field of a
  tool result, or a tool that returns it. It tells the agent not to guess
  the date. When no source exists, a tool or a wrapper that returns the
  current date and time zone is a change to the tools, not to the guide.
- **Define each relative period** that users ask for, as a filter:
  - "today", "yesterday": in which time zone;
  - "this week", "last week": the first day of the week, and whether the
    current week counts while it is not over;
  - "this month", "last month": calendar months;
  - "the last N days": a rolling window, and whether today counts.
- **Give a sample query for each common period form.** See
  [sample queries](references/improving_agents/techniques/guide-skill-for-a-tool-set/sample-queries.md).

## The bounds of a range

- **An inclusive start and an exclusive end** is the safe form: from the
  first moment of the range, to the first moment after it. A date-only
  end bound on a date-time field leaves out most of the last day.
- **Convert the time zone before you group by day.** A day in UTC and a day
  in the user's time zone start at different moments, so the rows of one
  day differ.
- **Daylight saving time** makes some days one hour shorter or longer in a
  local time zone. A count by hour or a rolling window of hours can be
  wrong on those days.

## Fiscal and business periods

When the business uses fiscal periods, state them in the glossary: the
first month of the fiscal year, the quarters, and the week rule if there
is one. A user who asks for "Q3" can mean the fiscal quarter, not the
calendar one.

## How fresh the data is

- **State how the data is loaded**: live, or loaded on a schedule with a
  lag.
- **An empty result for a recent range** can mean that the data is not
  loaded yet. The guide tells the agent how to find the latest date in the
  data, and to say so in the answer when the range is after it.

## What the answer states

Tell the agent to state the range it used, with its time zone, when the
question has a relative date ("from 3 March to 9 March, in UTC", with
invented dates). A user can then check the range. When the range is
computed by code, a wrapper can return it with the result: see
[directive in the tool response](references/improving_agents/techniques/directive-in-the-tool-response.md).

## A note on evals with relative dates

When an eval's expected answer depends on the current date ("last week"),
the expected answer changes with time on a live system. A failure on such
an item can be a problem of the eval, not of the guide. Check the date that
the eval assumed before you change the guide for it.
