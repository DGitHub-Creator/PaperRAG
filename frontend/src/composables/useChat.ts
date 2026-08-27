import { ref } from "vue"
import { authFetch } from "../services/api"
import { useWebSocket } from "./useWebSocket"
import { t } from "../i18n"

export interface RAGStep {
  icon?: string
  label: string
  detail?: string
}

export interface RAGTraceEntry {
  step: string
  label?: string
  score?: number
  time_ms?: number
  message?: string
}

export interface Message {
  text: string
  isUser: boolean
  isThinking?: boolean
  ragTrace?: RAGTraceEntry[] | null
  ragSteps?: RAGStep[]
  citations?: string[]
  unsupported?: string[]
}

// ── 模块级单例状态：App.vue / ChatView.vue 等多处调用共享同一份 ──
// 否则消息列表、加载态、会话 ID 会在组件间分裂
const messages = ref<Message[]>([])
const isLoading = ref(false)
const sessionId = ref("session_" + Date.now())
const abortController = ref<AbortController | null>(null)

let _scrollRaf = 0
function scrollToBottom(): void {
  if (_scrollRaf) return
  _scrollRaf = requestAnimationFrame(() => {
    _scrollRaf = 0
    const el = document.querySelector(".chat-container")
    if (el) el.scrollTop = el.scrollHeight
  })
}

function newChat(): void {
  messages.value = []
  sessionId.value = "session_" + Date.now()
}

function clearChat(): void {
  messages.value = []
}

function loadMessages(data: Message[] | unknown[]): void {
  messages.value = (data || []).map((msg: any) => ({
    text: msg.text ?? msg.content ?? "",
    isUser: msg.isUser ?? msg.type === "human",
    ragTrace: msg.ragTrace ?? msg.rag_trace ?? null,
    ragSteps: [],
  }))
  scrollToBottom()
}

function stop(): void {
  if (abortController.value) {
    abortController.value.abort()
  } else {
    const { isConnected, disconnect } = useWebSocket()
    if (isConnected.value) disconnect()
  }
}

function handleEvent(ev: any, botIdx: number): void {
  const msg = messages.value[botIdx]
  if (!msg) return
  if (ev.type === "content") {
    if (msg.isThinking) msg.isThinking = false
    msg.text += ev.content
  } else if (ev.type === "trace") {
    msg.ragTrace = ev.rag_trace
  } else if (ev.type === "rag_step") {
    msg.ragSteps!.push(ev.step)
  } else if (ev.type === "citations") {
    msg.citations = ev.citations
    msg.unsupported = ev.unsupported
  } else if (ev.type === "error") {
    msg.isThinking = false
    msg.text += `\n[Error: ${ev.content}]`
  }
}

async function send(text: string): Promise<void> {
  if (!text.trim() || isLoading.value) return

  messages.value.push({ text, isUser: true })
  scrollToBottom()

  isLoading.value = true
  const botIdx = messages.value.push({
    text: "", isUser: false, isThinking: true, ragTrace: null, ragSteps: [], citations: [], unsupported: [],
  }) - 1

  const { isConnected, send: wsSend } = useWebSocket()
  if (isConnected.value) {
    _wsBotIdx = botIdx
    wsSend({ message: text, session_id: sessionId.value })
    return
  }

  abortController.value = new AbortController()
  _wsBotIdx = -1

  try {
    const res = await authFetch("/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, session_id: sessionId.value }),
      signal: abortController.value.signal,
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    if (!res.body) throw new Error("Response body is null")

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ""

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      let idx: number
      while ((idx = buffer.indexOf("\n\n")) !== -1) {
        const line = buffer.slice(0, idx)
        buffer = buffer.slice(idx + 2)
        if (!line.startsWith("data: ")) continue
        const raw = line.slice(6)
        if (raw === "[DONE]") continue
        try {
          handleEvent(JSON.parse(raw), botIdx)
        } catch (_) { /* ignore parse errors */ }
      }
      scrollToBottom()
    }
  } catch (err: unknown) {
    const msg = messages.value[botIdx]
    if (!msg) return
    msg.isThinking = false
    if (err instanceof Error && err.name === "AbortError") {
      msg.text = msg.text || t("chat.aborted")
    } else {
      msg.text = `${t("chat.error_prefix")}${err instanceof Error ? err.message : String(err)}`
    }
  } finally {
    isLoading.value = false
    abortController.value = null
    scrollToBottom()
  }
}

// WS 模式下当前流式回复对应的 bot 消息索引
let _wsBotIdx = -1

function connectWs(token: string): void {
  const { connect } = useWebSocket()
  connect(token, (data: any) => {
    if (data.type === "done") {
      isLoading.value = false
    } else {
      handleEvent(data, _wsBotIdx)
      scrollToBottom()
    }
  })
}

function disconnectWs(): void {
  const { disconnect } = useWebSocket()
  disconnect()
}

export function useChat() {
  return { messages, isLoading, sessionId, newChat, clearChat, loadMessages, send, stop, connectWs, disconnectWs }
}
