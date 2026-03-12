import { indexedDBStore } from "./index_db_store"

type SkillsStoreState = {
  selected_skill_ids_by_task_id: Record<string, string[]>
}

const skills_store_key = "skills_store"
export const { store: skills_store, initialized: skills_store_initialized } =
  indexedDBStore<SkillsStoreState>(skills_store_key, {
    selected_skill_ids_by_task_id: {},
  })
