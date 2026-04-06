export type DocSkillResponse = {
  id: string
  name: string
  skill_name: string
  skill_content_header: string
  description: string | null
  extractor_config_id: string
  chunker_config_id: string
  document_tags: string[] | null
  skill_id: string | null
  strip_file_extensions: boolean
  is_archived: boolean
  created_at: string | null
  created_by: string | null
}
