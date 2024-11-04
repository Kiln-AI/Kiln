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
          secondary: "#000000",
          "secondary-content": "#ffffff",
          accent: "#E74D31",
          "accent-content": "#ffffff",
          neutral: "#e7e5e4",
          "neutral-content": "#000000",
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
      },
    ],
  },
}
