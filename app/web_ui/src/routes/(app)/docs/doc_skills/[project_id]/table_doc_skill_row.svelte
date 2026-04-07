<script lang="ts">
  import { goto } from "$app/navigation"
  import type { components } from "$lib/api_schema"

  type DocSkillResponse = components["schemas"]["DocSkillResponse"]

  export let doc_skill: DocSkillResponse
  export let project_id: string

  function open() {
    goto(`/docs/doc_skills/${project_id}/${doc_skill.id}/doc_skill`)
  }

  $: status_badge = doc_skill.is_archived
    ? { text: "Archived", class: "badge-secondary" }
    : doc_skill.skill_id
      ? { text: "Complete", class: "badge-outline badge-primary" }
      : { text: "Pending", class: "badge-outline badge-warning" }
</script>

<tr class="cursor-pointer hover:bg-base-200" on:click|stopPropagation={open}>
  <td class="align-top p-4">
    <div class="flex flex-col gap-2">
      <div class="font-medium">
        {doc_skill.name}
      </div>
      <div class="space-y-1 text-xs text-gray-500">
        {#if doc_skill.description}
          <div>{doc_skill.description}</div>
        {/if}
        <div class="flex flex-row flex-wrap gap-2 w-80">
          {#each doc_skill.document_tags || [] as tag}
            <div class="badge bg-gray-200 text-gray-500 text-xs">
              {tag}
            </div>
          {/each}
        </div>
      </div>
    </div>
  </td>

  <td class="p-4 align-top text-gray-500">
    {doc_skill.skill_name}
  </td>

  <td class="p-4 align-top">
    <div class="badge px-3 py-1 {status_badge.class}">
      {status_badge.text}
    </div>
  </td>
</tr>
