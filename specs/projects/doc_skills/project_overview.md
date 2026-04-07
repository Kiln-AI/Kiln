---
status: complete
---

# Doc Skills - Project Overview

We already have a RAG builder and Docs store built into Kiln. They allows:
- upload docs
- manage docs (tags, names)
- extract docs: VLLM based document extraction
- Create a RAG: select a doc tag, extractor, embedding model, chunking method. -> builds a RAG tool for you
- Manage RAG configs
- Use RAGs as a tool 

We already have [agent skills](https://agentskills.io/home) built into Kiln.
- Creates a SKILL.md file, and optional `/resources/**` files
- Exposes a tool to agents to call the skill
- Management/creation UI

I want to build on this infrastructure for a new project: “Docs to Skill”
- reuses upload/manage docs UX/APIs/models 
- New “Docs Skill” feature in the Docs & Search tab
  - Very similar to “Search Tools (RAG)” feature we have today in UX. 
  - “New Doc Skill” UX
    - Suggested templates like “New RAG”
    - Creation options page very similar to Rag. Select docs via tag and extractor just like RAD. No re-ranker, embedding model, or search index options.
    - Select chunking format: very much like rag UX, but the default size is much larger. 
    - “Search tool name” becomes “Skill name”
    - Description still there, but modified a bit (this is the index description). Pre-filled with a decent general one, but they can edit.
  - Datamodel:
    - DocumentSkill datamodel, like the search tools at a model
  - Manage UI
    - list of DocumentSkills
    - add button
    - click into details view.
  - Document Skill Details view: design pending
- Creation process 
  - UX: very similar to RAG (steps, show UI)
    - extract docs
    - chunk docs
    - New: create skill
  - Create Skill Step
    - We create a skill (we already have a datamodel defined for these)
    - Create the 
    - SKILL.md: the name and description, followed by an index/table-of-contents we build of all documents (see reference file parts). TBD table design (1 row per doc with “N parts” or 1 row per chunk)
    - add files: `references/[doc_name]/part[N].[md|txt]` - each chunk as a file. End of file should have something like `<<Document continues in references/[doc_name]/part[N+1].[md|txt] >>`
    - Create a DocSkill model: links to the skill by ID. DocSkill has the model that’s specific to DocSkill (description/chunking mode/extractor - options specific to DocSkills), while the Skill Model has the core skill data.
    - Note: we want a good deletion flow on any failures - roll back any created files.

Advanced Options for creating Docs to Skill
- “Remove file extensions (.pdf, etc)”: on by default, strips file extension from document names if they exist
- TBD: any more?

## Skill Tool

There should be no special tool integration for this. RAG required custom tools, but skills already have a tool. By creating a skill, it should “just work”.

## UI

UI Notes: This should be very similar to existing search tools UX/UI. 
- `/docs/[project_id]` add a “Doc Skills” entry point, similar to exiting search tools entry point
- Doc Skill list page: heavy inspiration from the RAG list page `/docs/rag_configs/[id]`
- Docs Skill Create pages: again, heavy inspiration from RAG pages
  - `/docs/rag_configs/[id]/add_search_tool`
  - `/docs/rag_configs/[id]/create_rag_config`
- Doc still detail page: heavy inspiration from RAG detail page `/docs/rag_configs/[proj id]/[id]/rag_config`
- DocSkills should link to Skill, and Skill should link to DocSkill in UI

## P2 Features

P2 features below should not be implemented until later phases. I want to design to allow for these

P2 Feature: Desc descriptions
- allow specifying a short description of docs in the doc manager UI. These go into the DocSkill index/table of contents. Limited in length.

P2 Feature: Semantic Doc Descriptions or Chunk Summaries
- Use AI to enhance the table of contents. Short descriptions of each doc, and each document part/chunk.
- Optional: 2 tiers of index
  - `SKILL.md` document index. Just doc names and descriptions, and “N parts”
  - `references/[doc name]/index.md` - table of contents for the doc, descriptions of each part.

