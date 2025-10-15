/** @type {import('tailwindcss').Config} */
import daisyui from "daisyui"
import typography from "@tailwindcss/typography"

export default {
  content: ["./src/**/*.{html,js,svelte,ts}"],
  theme: {
    extend: {},
  },
  plugins: [typography, daisyui],
  daisyui: {
    themes: [
      {
        kilntheme: {
          primary: "#415CF5",
          "primary-content": "#ffffff",
          secondary: "#131517",
          "secondary-content": "#ffffff",
          accent: "#E74D31",
          "accent-content": "#ffffff",
          neutral: "#e7e5e4",
          "neutral-content": "#131517",
          "base-100": "#ffffff",
          "base-200": "#F5F5F5",
          "base-300": "#bebebe",
          "base-content": "#161616",
          info: "#D7AAF9",
          "info-content": "#0a1616",
          success: "#33B79D",
          "success-content": "#ffffff",
          warning: "#F4B544",
          "warning-content": "#0a1616",
          error: "#E74D31",
          "error-content": "#ffffff",
        },
        kilnthemedark: {
          primary: "#415CF5",
          "primary-content": "#ffffff",
          secondary: "#131517",
          "secondary-content": "#ffffff",
          accent: "#E74D31",
          "accent-content": "#ffffff",
          neutral: "oklch(0.14 0.005 285.822998)",
          "base-100": "oklch(0.2533 0.016 252.419998)",
          "base-content": "oklch(0.97807 0.029 256.846985)",
        },
      },
    ],
  },
}
