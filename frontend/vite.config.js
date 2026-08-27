import { defineConfig } from "vite"
import vue from "@vitejs/plugin-vue"

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      // REST API 与 WebSocket 共用 /api 前缀，一并转发到后端
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        ws: true,
      },
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
})
