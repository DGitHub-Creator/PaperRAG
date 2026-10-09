// WS 通道（模块级单例，任何组件共享一条连接）。帧本体与 SSE 同源，解析复用 api/sse.ts。
import { ref } from "vue"
import { wsChatUrl } from "../api/ws"
import { parseStreamEvent } from "../api/sse"
import type { ChatRequest, StreamEvent } from "../api/types"

const isConnected = ref(false)

let socket: WebSocket | null = null
let onEvent: ((event: StreamEvent) => void) | null = null

export function useWebSocket() {
  function connect(token: string, handler: (event: StreamEvent) => void): void {
    disconnect()
    onEvent = handler
    const next = new WebSocket(wsChatUrl(token))
    next.onopen = () => {
      isConnected.value = true
    }
    next.onmessage = (message: MessageEvent) => {
      if (typeof message.data !== "string") return
      const event = parseStreamEvent(message.data)
      if (event) onEvent?.(event)
    }
    next.onerror = () => {
      isConnected.value = false
    }
    next.onclose = () => {
      isConnected.value = false
    }
    socket = next
  }

  function send(input: ChatRequest): void {
    if (socket && socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify(input))
  }

  function disconnect(): void {
    if (socket) {
      // 先摘除回调，避免主动关闭触发 onerror/onclose 副作用
      socket.onclose = null
      socket.onerror = null
      socket.onmessage = null
      socket.close()
      socket = null
    }
    onEvent = null
    isConnected.value = false
  }

  return { isConnected, connect, send, disconnect }
}
