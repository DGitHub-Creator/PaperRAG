import { defineConfig } from "vite"
import vue from "@vitejs/plugin-vue"

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      // REST API 与 WebSocket 共用 /api 前缀，一并转发到 **Go（go-api）** ——它是唯一公开入口。
      // Go 已接管的面（health/ready/auth）自己处理，尚未迁移的 sessions/chat/documents/ws
      // 由 Go 反代到 Python 上游（PYTHON_UPSTREAM，默认 127.0.0.1:8000）。
      "/api": {
        target: "http://127.0.0.1:8080",
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
