<script lang="ts">
  import { locale } from "svelte-i18n"
  import { browser } from "$app/environment"

  const languages = [
    { code: "en", name: "English", flag: "EN" },
    { code: "zh-CN", name: "简体中文", flag: "CN" },
    { code: "ja", name: "日本語", flag: "JP" },
    { code: "fr", name: "Français", flag: "FR" },
    { code: "ru", name: "Русский", flag: "RU" },
  ]

  function changeLanguage(lang: string) {
    locale.set(lang)
    if (browser) {
      localStorage.setItem("locale", lang)
    }
  }

  function getCurrentLanguage() {
    return languages.find((lang) => lang.code === $locale) || languages[0]
  }
</script>

<div class="dropdown dropdown-end">
  <div
    tabindex="0"
    role="button"
    class="btn btn-ghost flex items-center"
    style="min-width: 14rem"
  >
    <span
      class="text-xs font-bold bg-gray-200 text-gray-700 px-1.5 py-0.5 rounded"
      >{getCurrentLanguage().flag}</span
    >
    <span class="inline ml-2">{getCurrentLanguage().name}</span>
    <svg
      class="w-4 h-4 ml-auto"
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
    >
      <path
        stroke-linecap="round"
        stroke-linejoin="round"
        stroke-width="2"
        d="M19 9l-7 7-7-7"
      ></path>
    </svg>
  </div>
  <ul
    class="dropdown-content z-[1] menu p-2 shadow bg-base-100 rounded-box w-52"
  >
    {#each languages as language}
      <li>
        <button
          class="flex items-center gap-2 {$locale === language.code
            ? 'active'
            : ''}"
          on:click={() => changeLanguage(language.code)}
        >
          <span
            class="text-xs font-bold bg-gray-200 text-gray-700 px-1.5 py-0.5 rounded"
            >{language.flag}</span
          >
          <span>{language.name}</span>
          {#if $locale === language.code}
            <svg
              class="w-4 h-4 ml-auto"
              fill="currentColor"
              viewBox="0 0 20 20"
            >
              <path
                fill-rule="evenodd"
                d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                clip-rule="evenodd"
              ></path>
            </svg>
          {/if}
        </button>
      </li>
    {/each}
  </ul>
</div>
