/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{vue,js,ts,jsx,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      fontFamily: {
        sans: [
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Microsoft JhengHei",
          "PingFang TC",
          "sans-serif",
        ],
      },
      colors: {
        // Centralized brand palette. Change once, propagates everywhere.
        brand: {
          DEFAULT: "#4c8bf5",
          dark: "#3b7ae0",
          subtle: "#a8c4ff",
        },
        surface: {
          0: "#0f1115",
          1: "#161a22",
          2: "#1d2230",
          border: "#2a2f3a",
        },
        ink: {
          high: "#e8eaed",
          mid: "#c4c7cc",
          low: "#9aa0a6",
          faint: "#6f7682",
        },
      },
    },
  },
  plugins: [],
};
