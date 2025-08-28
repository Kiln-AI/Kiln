import { indexedDBStore } from "./index_db_store"

type ToolsStore = {
  selected_tool_ids_by_task_id: Record<string, string[]>
}

const tools_store_key = "tools_store"
export const { store: tools_store, initialized: tools_store_initialized } =
  indexedDBStore<ToolsStore>(tools_store_key, {
    selected_tool_ids_by_task_id: {},
  })
