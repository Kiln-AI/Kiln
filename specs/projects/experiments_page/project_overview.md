---
status: complete
---

# Experiments Page

Add an "Experiments" page to the web app. It shows the lineage graph of every run config for a task: one graph point per run config, linked to the run config it was derived from. The goal is to show the breadth of experimentation on a task and how the agent evolved over time.

This is not a new compare screen. It is just the lineage graph, on a new screen. Leave the existing compare screen as is.

## Inspiration, not a starting point

Mike built a prototype on branch `mike/compare-map-view` (the `/evolution/[project_id]/[task_id]` route, map view). Mike didn't use the standard dev process, so we want a clean build. He's also not a developer, so we're not sure he chose the best libraries and approaches. We should redesign with his work as inspiration, not build from it.

## UI and design

- The attached mock (`reference_mock.webp`, "All the things we tried") is quite decent. It gives the idea of the goal. Probably put the stats on top, and make the graph fill the space below.
- Mike's prototype is good in some ways and not in others:
  - No expand button like Mike's.
  - Follow our style guide more directly. His didn't.
  - His graph is attractive, but the colors aren't the Kiln palette.
  - He added libraries.

## Navigation

- No top-level link in the left sidebar. Leave that to Compare.
- Link to this page from the run config list on the Optimize page, and from the Compare page.

## Technical

- We use echarts. Should we use it, or build our own? Would a new dependency be a good choice?
- Check Mike's classifier code for "Changed the prompt, tools or skills" vs "Changed the model or its settings".
- Those two types of change aren't mutually exclusive, and the prototype groups prompt, tools and skills into one. Instead, detect each kind of change separately, and use a visual that can show more than one kind of change on the same run config.
