import { browser } from "$app/environment"
import { init, register } from "svelte-i18n"

const defaultLocale = "en"

register("en", () => import("./locales/en.json"))
register("zh-CN", () => import("./locales/zh-CN.json"))
register("ja", () => import("./locales/ja.json"))
register("fr", () => import("./locales/fr.json"))
register("ru", () => import("./locales/ru.json"))

// 获取初始语言设置
function getInitialLocale() {
  if (browser) {
    // 首先检查本地存储
    const stored = localStorage.getItem("locale")
    if (stored && ["en", "zh-CN", "ja", "fr", "ru"].includes(stored)) {
      return stored
    }

    // 然后检查浏览器语言
    const browserLang = window.navigator.language
    if (browserLang.startsWith("zh")) {
      return "zh-CN"
    }
    if (browserLang.startsWith("ja")) {
      return "ja"
    }
    if (browserLang.startsWith("fr")) {
      return "fr"
    }
    if (browserLang.startsWith("ru")) {
      return "ru"
    }
  }

  return defaultLocale
}

init({
  fallbackLocale: defaultLocale,
  initialLocale: getInitialLocale(),
})
