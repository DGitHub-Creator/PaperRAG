// WebSocket 的 URL 也归 api 层（`docs/rules/10-frontend-structure.md` F1）：路径与 BASE 同源，
// 换前缀时不用再回忆"还有一处手拼 location.host"。
import { BASE } from "./http"

/** 浏览器 WebSocket 带不了 Authorization 头，契约规定 token 走 query 参数（openapi.yaml: wsChat） */
export function wsChatUrl(token: string): string {
  const protocol = location.protocol === "https:" ? "wss:" : "ws:"
  return `${protocol}//${location.host}${BASE}/ws/chat?token=${encodeURIComponent(token)}`
}
