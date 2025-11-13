import globals from "globals"
import js from "@eslint/js"
import tsParser from "@typescript-eslint/parser"
import typescriptEslint from "@typescript-eslint/eslint-plugin"
import sveltePlugin from "eslint-plugin-svelte"
import svelteParser from "svelte-eslint-parser"
import prettier from "eslint-config-prettier"

export default [
  {
    ignores: [
      "**/.DS_Store",
      "**/node_modules",
      "**/build",
      "**/.svelte-kit",
      "**/package",
      "**/.env",
      "**/.env.*",
      "!**/.env.example",
      "**/pnpm-lock.yaml",
      "**/package-lock.json",
      "**/yarn.lock",
    ],
  },
  js.configs.recommended,
  prettier,
  {
    languageOptions: {
      parser: tsParser,
      sourceType: "module",
      ecmaVersion: 2020,

      parserOptions: {
        extraFileExtensions: [".svelte"],
      },

      globals: {
        ...globals.browser,
        ...globals.node,
      },
    },

    plugins: {
      "@typescript-eslint": typescriptEslint,
    },

    rules: {
      ...typescriptEslint.configs.recommended.rules,

      // no-undef has been turned off because of this:
      // basically, it causes issues and TS does those checks so it's redundant
      // https://typescript-eslint.io/linting/troubleshooting#i-get-errors-from-the-no-undef-rule-about-global-variables-not-being-defined-even-though-there-are-no-typescript-errors
      "no-undef": "off",

      // Default eslint no-unused-vars modified to ignore underscore vars which we use for known unused vars
      "no-unused-vars": "off",
      "@typescript-eslint/no-unused-vars": [
        "error",
        {
          argsIgnorePattern: "^_$",
          varsIgnorePattern: "^_$",
          caughtErrorsIgnorePattern: "^_$",
        },
      ],

      // Don't allow console.log (but allow console.error/warn/info)
      "no-console": [
        "error",
        {
          allow: ["warn", "error", "info"],
        },
      ],
    },
  },
  {
    files: ["**/*.svelte"],

    plugins: {
      svelte: sveltePlugin,
    },

    languageOptions: {
      parser: svelteParser,

      parserOptions: {
        parser: {
          ts: "@typescript-eslint/parser",
          js: "espree",
          typescript: "@typescript-eslint/parser",
        },
      },
    },

    rules: {
      ...sveltePlugin.configs.recommended.rules,
      // Svelte uses self-assignment to trigger reactivity, we don't want to lint them.
      "no-self-assign": "off",
      // Functions in <script> tags are not "inner declarations" in the problematic sense. Ignore in svelte files.
      "no-inner-declarations": "off",
    },
  },
]
