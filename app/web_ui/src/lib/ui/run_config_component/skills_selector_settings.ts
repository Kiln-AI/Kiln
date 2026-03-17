export interface SkillsSelectorSettings {
  mandatory_skills: string[] | null
  description: string | undefined
  info_description: string | undefined
  hide_info_description: boolean
  disabled: boolean
  empty_label: string | undefined
  optional: boolean
}
