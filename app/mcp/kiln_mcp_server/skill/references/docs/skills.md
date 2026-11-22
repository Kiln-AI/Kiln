---
description: Load more instructions, depending on the goal (Progressive Prompt Enhancement)
icon: puzzle-piece
online_url: https://docs.kiln.tech/docs/skills
---

# Skills

Skills are reusable instructions that your agents can load on-demand. Unlike prompts which are always included in your agent's context, skills are only retrieved when the agent decides they're needed. This makes skills perfect for specialized knowledge, detailed procedures, or domain expertise that you don't want cluttering every single run.

### Creating Skills

Skills are created at the project level, and can be used by any task within that project.

To create a new skill, navigate to the "Skills" page in your project sidebar and click "New Skill".

You'll be prompted to provide:

* **Name**: An identifier for the skill. Only allows lower case letters, numbers and hyphens.
* **Description**: A clear explanation of what the skill does and when to use it
* **Instructions**: The markdown-formatted instructions that will be loaded when the agent calls this skill.

{% hint style="warning" %}
**Write Clear Descriptions**

The skill description is what the model sees when deciding whether to use a skill. Make it specific and actionable:

* **Poor:** "SQL help"
* **Better:** "Write and optimize SQL queries for PostgreSQL"
* **Best:** "Generates SQL queries for PostgreSQL with proper joins, filtering, and performance optimization. Use when user requests data retrieval, filtering, or analysis from a database."
{% endhint %}

### Using Skills

Once you've created skills, you can make them available to your agents through run configurations.

#### Adding Skills to Run Configurations

On the "Run" screen, under the "Skills" section in Advanced, you'll see all available skills in your project. Select the skills you want to make available to the agent for this run.

#### How Agents Use Skills

When you make skills available to an agent, here's what happens:

1. **Discovery**: The agent sees all available skill names and descriptions at the end of its system prompt.
2. **Decision**: The agent decides which skills (if any) are relevant to the current task.
3. **Loading**: When the agent needs a skill, it calls the `skill()` tool with the skill's name.
4. **Execution**: The skill's full instructions are loaded into the conversation, and the agent proceeds with the task.

This lazy-loading approach means your agent's context stays clean and focused. Specialized instructions are only retrieved when actually needed.

{% hint style="info" %}
**Model Behavior**

The model may or may not choose to use the skills you provide. If you find the model is not using a skill when you feel it should, try:

1. Making the skill description more specific and actionable
2. Updating your prompt to explicitly mention when certain skills should be used
3. Ensuring the skill name clearly indicates its purpose
4. Using a more modern model: models that came out before Agent Skills were released have not seen skills in their training data, and are less likely to leverage them.
{% endhint %}

#### Viewing Skill Usage

When viewing a run trace, you can see which skills the agent loaded in the "All Messages" section. Skill calls appear as tool invocations, showing when and how the agent used each skill.

### Reference Files

Skills can include reference files—additional markdown documents that provide supporting information, which are also only retrieved when the agent decides they're needed. References are useful for:

* Detailed technical specifications
* Code examples or templates
* Domain knowledge or terminology
* Style guides or formatting rules

#### Adding References

Currently, references are managed through the file system. To add references to a skill:

1. Navigate to your project's `skills` directory
2. Find the skill's folder (named after the skill ID)
3. Create a `references` folder if it doesn't exist
4. Add markdown files (`.md`) to the `references` folder
5. Reference the new file from your main SKILL.md file (see details below).

Your skill structure should look like:

```
skills/
  <skill_id>/
    skill.kiln           # Metadata (name, description, etc.)
    SKILL.md             # Main skill instructions
    references/          # Additional reference files
      API_RESPONSE_FORMAT.md
      STYLE_GUIDE.md
      ...
```

#### Referencing from SKILL.md

Within your skill instructions (in `SKILL.md`), you should reference files using markdown link syntax. This is how the agent can discover reference files. Example:

{% code overflow="wrap" %}
```markdown
## Instructions

Follow our company's coding standards. See our [style guide](references/STYLE_GUIDE.md) for details.

When generating API responses, use the format specified in this [API format guide](references/API_RESPONSE_FORMAT.md).
```
{% endcode %}

### Skills vs Tools vs Subtasks

Kiln offers three ways to extend your agent's capabilities. Here's how to choose:

<table data-full-width="true"><thead><tr><th>Feature</th><th>Skills</th><th>Tools</th><th>Subtasks</th></tr></thead><tbody><tr><td><strong>Primary Use</strong></td><td>Instructions &#x26; knowledge</td><td>External actions</td><td>Complex workflows</td></tr><tr><td><strong>Context Impact</strong></td><td>Details loaded only when needed. Only description injected into prompt.</td><td>Tool definitions often much more verbose than skills descriptions</td><td>Isolated per subtask</td></tr><tr><td><strong>Progressive Disclosure</strong></td><td>Yes - can link to reference files, forming a nested hierarchy of knowledge</td><td>No</td><td>No</td></tr><tr><td><strong>Best For</strong></td><td>Guidelines, procedures, rules</td><td>APIs, databases</td><td>Multi-agent patterns</td></tr><tr><td><strong>Setup Complexity</strong></td><td>Low</td><td>Medium</td><td>High</td></tr></tbody></table>

### Skills vs Search Tools (RAG)

Skills can also be compared to [RAG](references/docs/documents-and-search-rag.md). Both have pros and cons for adding knowledge to a system:

<table data-full-width="true"><thead><tr><th>Feature</th><th>Skills</th><th>RAG</th></tr></thead><tbody><tr><td><strong>Max Documents</strong></td><td>Typically &#x3C;50</td><td>Unlimited</td></tr><tr><td><strong>Context Impact</strong></td><td>Low: ~100 tokens per document for name and description.</td><td>Very Low: 1 tool definition for all documents.</td></tr><tr><td><strong>Chunking</strong></td><td>Manually create skills and reference files.</td><td>Automatic chunking of larger docs.</td></tr><tr><td><strong>Control</strong></td><td>High: define the exact skill and reference file content. Descriptions can prompt the agent exactly when to load each skill.</td><td>Low: documents are automatically chunked (split) and indexed. The agent needs to guess search terms to find relevant information.</td></tr><tr><td><strong>Deployment Complexity</strong></td><td>Low: no additional effort if your toolchain supports it (like <a href="https://docs.kiln.tech/developers/python-library-quickstart">Kiln SDK</a>).</td><td>High: requires vector database hosting, and jobs to process and index documents.</td></tr><tr><td><strong>Progressive Disclosure</strong></td><td>Yes - can link to reference files, forming a nested hierarchy of knowledge</td><td>Yes - can multi-hop.</td></tr></tbody></table>

### Best Practices

#### Write Specific, Actionable Descriptions

Your skill descriptions are the primary signal the model uses to decide when to use a skill. Make them clear and specific:

* ✅ "Validates JSON schemas against the OpenAPI 3.0 specification and reports errors"
* ❌ "JSON validator"

#### Keep Skills Focused

Each skill should have a single, clear purpose. If you find a skill becoming too broad, consider splitting it into multiple focused skills, or splitting the skill into [reference files](references/docs/skills.md#reference-files).

#### Test Your Skills

After creating a skill, test it by:

1. Creating a run configuration with the skill enabled
2. Running your task with inputs that should trigger the skill
3. Checking the trace to verify the skill was loaded and used correctly

### Managing Skills

#### Editing / Cloning Skills

We don't allow editing skills, as historical eval scores and dataset runs become would become misleading if edited, with no versioning to tell you what changed.

Instead, Kiln lets you clone a skill, giving you a fresh copy to modify while keeping the original intact so existing results stay valid.

#### Archiving Skills

If you have skills you no longer use but want to keep for reference, you can archive them. Archived skills won't appear in the skills dropdown and won't be available to agents. Unarchiving restores them to active use.
