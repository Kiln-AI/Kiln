---
status: complete
---

# Chat App State


We’re adding a chat agent to Kiln. One of the things we want it to do is to send a header at the top of a user message, but only if the context has change.

Example
```
<new_app_ui_context>
Path: /tools/189194447825/add_tools
Page Name: Settings Home
Page Descipton: A page is for managing user settings. General selection screen with many options.
Current Project: 12345
Currnet Task: 123456
</new_app_ui_context>
```

Details:
- Add a agentInfo store (see below)
- Add `lastSentAppState` (or similar) property to the chat store. `app/web_ui/src/lib/chat/chat_session_store.ts‎`
- When sending a new message:
  - gets current app state via agentInfo, and UIState (for project ID and task ID)
  - gets last sent state via chat_session_store
  - if it’s changed, prepend the message format for new_app_ui_context to the message, and update chat_session_store lastSentAppState
- Separate phase: Backfill all missing pages + add CI check, to make sure we don’t miss it anywhere. Be descriptive, giving the agent what it needs to know. 
  - explain IDs in path “project id X”, “task ID Y”, tool ids, etc. 
  - explain the purpose of the page
  - Explain key data, for example if looking at a tool server definition, the tool server name is a good detail to add. If looking at dataset and has filter applies the filter is good to add. Don’t add all information. Just the most essential info.

We’ll implement this with a store:
```
// $lib/agent.ts
import { writable } from 'svelte/store';

export interface AgentPageInfo {
  name: string;
  description: string;
}

export const agentInfo = writable<AgentPageInfo | null>(null);
```

In each page we’ll set the information. It can be a static string “This is the tools homepage, with options to add and manage MCP tools.”, or dynamic where appropriate. “This is a ‘tools detail page’ for the tool ID 100945512896 in project 1234545, named ‘Memory by Anthropic’”
```
<!-- +page.svelte --> 
<script> 
  import { agentInfo } from '$lib/agent'
  agentInfo.set({
    name: "Settings"
    description: "A page is for managing user settings. General selection screen with many options."
  })
</script>
```


Add a test to check each page has it (rough idea, untested) as part of the last phase.
```
// src/lib/agent.test.ts
import { describe, it, expect } from 'vitest';
import { readdirSync, readFileSync } from 'fs';
import { join } from 'path';

function findPageFiles(dir: string): string[] {
  const results: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const fullPath = join(dir, entry.name);
    if (entry.isDirectory()) {
      results.push(...findPageFiles(fullPath));
    } else if (entry.name === '+page.svelte') {
      results.push(fullPath);
    }
  }
  return results;
}

describe('agentInfo metadata', () => {
  const routesDir = join(process.cwd(), 'src', 'routes');
  const pages = findPageFiles(routesDir);

  it('should find at least one page', () => {
    expect(pages.length).toBeGreaterThan(0);
  });

  for (const page of pages) {
    const relativePath = page.replace(process.cwd() + '/', '');
    it(`${relativePath} should set agentInfo`, () => {
      const content = readFileSync(page, 'utf-8');
      expect(
        content.includes('agentInfo.set(') || content.includes('agentInfo.update('),
        `Missing agentInfo.set() call in ${relativePath}`
      ).toBe(true);
    });
  }
});
```