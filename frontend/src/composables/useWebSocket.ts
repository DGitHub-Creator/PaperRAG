import { ref } from "vue"
import { t } from "../i18n"

export function useWebSocket() {
  const ws = ref<WebSocket | null>(null)
  const isConnected = ref(false)

  function connect(token: string, onMessage: (data: unknown) => void, onError?: (msg: string) => void): void {
    if (ws.value) disconnect()
    const protocol = location.protocol === "https:" ? "wss:" : "ws:"
    const url = `${protocol}//${location.host}/ws/chat?token=${encodeURIComponent(token)}`
    const socket = new WebSocket(url)
    socket.onopen = () => { isConnected.value = true }
    socket.onmessage = (ev: MessageEvent) => {
      try { onMessage(JSON.parse(ev.data)) }
      catch (_) { /* ignore parse errors */ }
    }
    socket.onerror = () => { isConnected.value = false; onError?.(t("ws.error")) }
    socket.onclose = () => { isConnected.value = false }
    ws.value = socket
  }

  function send(data: unknown): void {
    if (ws.value?.readyState === WebSocket.OPEN) {
      ws.value.send(JSON.stringify(data))
    }
  }

  function disconnect(): void {
    if (ws.value) { ws.value.close(); ws.value = null }
    isConnected.value = false
  }

  return { ws, isConnected, connect, send, disconnect }
}
