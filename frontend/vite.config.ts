import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import { fileURLToPath, URL } from "node:url";

// Vite config for Stock News Hub frontend.
//   - dev: serve on :5173, proxy /api to local FastAPI on :8000
//   - build: emit into ../docs so FastAPI on Vercel can serve it
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: {
      // Default: hit the live Vercel API so `npm run dev` "just works"
      // without needing FastAPI running locally. Override target to
      // http://127.0.0.1:8000 if you're editing the backend too.
      "/api": {
        target: "https://stock-news-hub.vercel.app",
        changeOrigin: true,
        secure: true,
      },
    },
  },
  build: {
    outDir: "../docs",
    emptyOutDir: true,
    sourcemap: false,
  },
});
