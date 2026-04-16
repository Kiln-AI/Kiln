/**
 * Lightweight translation system for Kiln.
 *
 * This is NOT a full i18n framework. It strategically translates key UI
 * strings (sidebar labels, important buttons) that browser translation
 * extensions handle poorly. The vast majority of the app is left for
 * browser extensions to translate.
 *
 * To add a new translation key:
 *   1. Add the English string to the `en` object below
 *   2. Add translations for other languages
 *   3. Use `$t('key')` in your Svelte component
 *
 * To add a new language:
 *   1. Add a new entry to `translations` with the language code as key
 *   2. Translate the strings (only translate what you can — missing keys
 *      fall back to English automatically)
 */

export type SupportedLocale = "en" | "es" | "zh" | "ja" | "ko" | "fr" | "de" | "pt"

export const localeNames: Record<SupportedLocale, string> = {
  en: "English",
  es: "Español",
  zh: "中文",
  ja: "日本語",
  ko: "한국어",
  fr: "Français",
  de: "Deutsch",
  pt: "Português",
}

type TranslationStrings = Record<string, string>

const translations: Record<SupportedLocale, TranslationStrings> = {
  en: {
    // Sidebar navigation
    "nav.run": "Run",
    "nav.dataset": "Dataset",
    "nav.specs_evals": "Specs & Evals",
    "nav.optimize": "Optimize",
    "nav.prompts": "Prompts",
    "nav.models": "Models",
    "nav.tools": "Tools",
    "nav.skills": "Skills",
    "nav.docs_search": "Docs & Search",
    "nav.fine_tune": "Fine Tune",
    "nav.synthetic_data": "Synthetic Data",
    "nav.settings": "Settings",
    // Common actions
    "action.retry": "Retry",
    "action.save": "Save",
    "action.cancel": "Cancel",
    "action.delete": "Delete",
    "action.create": "Create",
    // Errors
    "error.loading_projects": "Error loading projects",
  },
  es: {
    "nav.run": "Ejecutar",
    "nav.dataset": "Datos",
    "nav.specs_evals": "Specs y Evals",
    "nav.optimize": "Optimizar",
    "nav.prompts": "Prompts",
    "nav.models": "Modelos",
    "nav.tools": "Herramientas",
    "nav.skills": "Habilidades",
    "nav.docs_search": "Docs y Búsqueda",
    "nav.fine_tune": "Ajuste Fino",
    "nav.synthetic_data": "Datos Sintéticos",
    "nav.settings": "Configuración",
    "action.retry": "Reintentar",
    "action.save": "Guardar",
    "action.cancel": "Cancelar",
    "action.delete": "Eliminar",
    "action.create": "Crear",
    "error.loading_projects": "Error al cargar proyectos",
  },
  zh: {
    "nav.run": "运行",
    "nav.dataset": "数据集",
    "nav.specs_evals": "规范与评估",
    "nav.optimize": "优化",
    "nav.prompts": "提示词",
    "nav.models": "模型",
    "nav.tools": "工具",
    "nav.skills": "技能",
    "nav.docs_search": "文档与搜索",
    "nav.fine_tune": "微调",
    "nav.synthetic_data": "合成数据",
    "nav.settings": "设置",
    "action.retry": "重试",
    "action.save": "保存",
    "action.cancel": "取消",
    "action.delete": "删除",
    "action.create": "创建",
    "error.loading_projects": "加载项目时出错",
  },
  ja: {
    "nav.run": "実行",
    "nav.dataset": "データセット",
    "nav.specs_evals": "仕様と評価",
    "nav.optimize": "最適化",
    "nav.prompts": "プロンプト",
    "nav.models": "モデル",
    "nav.tools": "ツール",
    "nav.skills": "スキル",
    "nav.docs_search": "ドキュメントと検索",
    "nav.fine_tune": "ファインチューニング",
    "nav.synthetic_data": "合成データ",
    "nav.settings": "設定",
    "action.retry": "再試行",
    "action.save": "保存",
    "action.cancel": "キャンセル",
    "action.delete": "削除",
    "action.create": "作成",
    "error.loading_projects": "プロジェクトの読み込みエラー",
  },
  ko: {
    "nav.run": "실행",
    "nav.dataset": "데이터셋",
    "nav.specs_evals": "사양 및 평가",
    "nav.optimize": "최적화",
    "nav.prompts": "프롬프트",
    "nav.models": "모델",
    "nav.tools": "도구",
    "nav.skills": "스킬",
    "nav.docs_search": "문서 및 검색",
    "nav.fine_tune": "파인튜닝",
    "nav.synthetic_data": "합성 데이터",
    "nav.settings": "설정",
    "action.retry": "재시도",
    "action.save": "저장",
    "action.cancel": "취소",
    "action.delete": "삭제",
    "action.create": "만들기",
    "error.loading_projects": "프로젝트 로딩 오류",
  },
  fr: {
    "nav.run": "Exécuter",
    "nav.dataset": "Jeu de données",
    "nav.specs_evals": "Spécs et Évals",
    "nav.optimize": "Optimiser",
    "nav.prompts": "Prompts",
    "nav.models": "Modèles",
    "nav.tools": "Outils",
    "nav.skills": "Compétences",
    "nav.docs_search": "Docs et Recherche",
    "nav.fine_tune": "Affinage",
    "nav.synthetic_data": "Données Synthétiques",
    "nav.settings": "Paramètres",
    "action.retry": "Réessayer",
    "action.save": "Enregistrer",
    "action.cancel": "Annuler",
    "action.delete": "Supprimer",
    "action.create": "Créer",
    "error.loading_projects": "Erreur lors du chargement des projets",
  },
  de: {
    "nav.run": "Ausführen",
    "nav.dataset": "Datensatz",
    "nav.specs_evals": "Specs & Evals",
    "nav.optimize": "Optimieren",
    "nav.prompts": "Prompts",
    "nav.models": "Modelle",
    "nav.tools": "Werkzeuge",
    "nav.skills": "Fähigkeiten",
    "nav.docs_search": "Docs & Suche",
    "nav.fine_tune": "Feintuning",
    "nav.synthetic_data": "Synthetische Daten",
    "nav.settings": "Einstellungen",
    "action.retry": "Erneut versuchen",
    "action.save": "Speichern",
    "action.cancel": "Abbrechen",
    "action.delete": "Löschen",
    "action.create": "Erstellen",
    "error.loading_projects": "Fehler beim Laden der Projekte",
  },
  pt: {
    "nav.run": "Executar",
    "nav.dataset": "Conjunto de Dados",
    "nav.specs_evals": "Specs e Evals",
    "nav.optimize": "Otimizar",
    "nav.prompts": "Prompts",
    "nav.models": "Modelos",
    "nav.tools": "Ferramentas",
    "nav.skills": "Habilidades",
    "nav.docs_search": "Docs e Pesquisa",
    "nav.fine_tune": "Ajuste Fino",
    "nav.synthetic_data": "Dados Sintéticos",
    "nav.settings": "Configurações",
    "action.retry": "Tentar Novamente",
    "action.save": "Salvar",
    "action.cancel": "Cancelar",
    "action.delete": "Excluir",
    "action.create": "Criar",
    "error.loading_projects": "Erro ao carregar projetos",
  },
}

/**
 * Look up a translation key for the given locale.
 * Falls back to English if the key is missing in the target locale.
 * Returns the key itself if not found in any locale.
 */
export function translate(locale: SupportedLocale, key: string): string {
  return translations[locale]?.[key] ?? translations.en[key] ?? key
}
