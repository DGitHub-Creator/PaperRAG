import { ref } from "vue"
import { t } from "../i18n"

// ── 模块级单例状态：任何组件调用 useWebSocket() 共享同一连接 ──
const ws = ref<WebSocket | null>(null)
const isConnected = ref(false)
const _token = ref<string>("")
const _onMessage = ref<((data: unknown) => void) | null>(null)
const _onError = ref<((msg: string) => void) | null>(null)

/** 后端 WS 路由：/api/v1/ws/chat（与 REST API 同前缀，代理层统一转发） */
function buildWsUrl(token: string): string {
  const protocol = location.protocol === "https:" ? "wss:" : "ws:"
  return `${protocol}//${location.host}/api/v1/ws/chat?token=${encodeURIComponent(token)}`
}

function _openSocket(): void {
  const socket = new WebSocket(buildWsUrl(_token.value))
  socket.onopen = () => { isConnected.value = true }
  socket.onmessage = (ev: MessageEvent) => {
    try { _onMessage.value?.(JSON.parse(ev.data)) }
    catch (_) { /* ignore parse errors */ }
  }
  socket.onerror = () => {
    isConnected.value = false
    _onError.value?.(t("ws.error"))
  }
  socket.onclose = () => { isConnected.value = false }
  ws.value = socket
}

export function useWebSocket() {
  function connect(token: string, onMessage: (data: unknown) => void, onError?: (msg: string) => void): void {
    if (ws.value) disconnect()
    _token.value = token
    _onMessage.value = onMessage
    _onError.value = onError ?? null
    _openSocket()
  }

  function send(data: unknown): void {
    if (ws.value?.readyState === WebSocket.OPEN) {
      ws.value.send(JSON.stringify(data))
    }
  }

  function disconnect(): void {
    if (ws.value) {
      // 先摘除回调，避免主动关闭触发 onerror/onclose 副作用
      if (ws.value) ws.value.onclose = null
      ws.value.close()
      ws.value = null
    }
    isConnected.value = false
    _onMessage.value = null
    _onError.value = null
  }

  return { ws, isConnected, connect, send, disconnect }
}
