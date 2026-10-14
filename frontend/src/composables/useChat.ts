// 聊天状态（模块级单例）：不认识 DOM、不认识对话框，滚动与提示由组件负责（`docs/rules/10-frontend-structure.md` R3/R4）。
import { ref } from "vue"
import * as api from "../api/client"
import { t } from "../i18n"
import { describeError, isAbortError } from "../utils/errors"
import { useWebSocket } from "./useWebSocket"
import type { CitationItem, MessageInfo, RagStep, RagTrace, StreamEvent } from "../api/types"

export interface ChatMessage {
  text: string
  isUser: boolean
  isThinking: boolean
  ragSteps: RagStep[]
  ragTrace: RagTrace | null
  citations: CitationItem[]
  unsupported: CitationItem[]
}

const messages = ref<ChatMessage[]>([])
const isLoading = ref(false)
const sessionId = ref(newSessionId())
/** 每次消息内容变化 +1：组件 watch 它来滚动，状态层因此不需要认识 DOM */
const revision = ref(0)

let abortController: AbortController | null = null
// WS 模式下流式回复落在哪条消息上（SSE 模式用闭包里的索引）
let wsTargetIndex = -1

function newSessionId(): string {
  return `session_${Date.now()}`
}

function blankReply(): ChatMessage {
  return { text: "", isUser: false, isThinking: true, ragSteps: [], ragTrace: null, citations: [], unsupported: [] }
}

function applyEvent(event: StreamEvent, index: number): void {
  const msg = messages.value[index]
  if (!msg) return
  switch (event.type) {
    case "content":
      msg.isThinking = false
      msg.text += event.content
      break
    case "rag_step":
      msg.ragSteps.push(event.step)
      break
    case "trace":
      msg.ragTrace = event.rag_trace ?? null
      break
    case "citations":
      msg.citations = event.citations || []
      msg.unsupported = event.unsupported || []
      break
    case "error":
      msg.isThinking = false
      msg.text += `\n[${t("chat.error_prefix")}${event.content}]`
      break
    case "done":
      msg.isThinking = false
      isLoading.value = false
      break
  }
  revision.value += 1
}

export function useChat() {
  function newChat(): void {
    messages.value = []
    sessionId.value = newSessionId()
    revision.value += 1
  }

  function clearChat(): void {
    messages.value = []
    revision.value += 1
  }

  /** 历史会话记录 → 消息列表（契约里 rag_trace 是对象，不是数组） */
  function loadHistory(records: MessageInfo[]): void {
    messages.value = records.map((record) => ({
      text: record.content,
      isUser: record.type === "human",
      isThinking: false,
      ragSteps: [],
      ragTrace: record.rag_trace ?? null,
      citations: [],
      unsupported: [],
    }))
    revision.value += 1
  }

  function selectSession(id: string): void {
    sessionId.value = id
  }

  function stop(): void {
    if (abortController) {
      abortController.abort()
      return
    }
    // As-Is 语义：WS 模式下"停止"就是断链（下一条消息会退回 SSE）。改动留给 P1-4 流式接管。
    const ws = useWebSocket()
    if (ws.isConnected.value) ws.disconnect()
  }

  async function send(text: string): Promise<void> {
    const content = text.trim()
    if (!content || isLoading.value) return

    messages.value.push({ text: content, isUser: true, isThinking: false, ragSteps: [], ragTrace: null, citations: [], unsupported: [] })
    const index = messages.value.push(blankReply()) - 1
    revision.value += 1
    isLoading.value = true

    const ws = useWebSocket()
    if (ws.isConnected.value) {
      wsTargetIndex = index
      ws.send({ message: content, session_id: sessionId.value })
      return
    }

    const controller = new AbortController()
    abortController = controller
    try {
      await api.chatStream({ message: content, session_id: sessionId.value }, controller.signal, (event) => applyEvent(event, index))
    } catch (err: unknown) {
      const msg = messages.value[index]
      if (msg) {
        msg.isThinking = false
        if (isAbortError(err)) msg.text = msg.text || t("chat.aborted")
        else msg.text = `${t("chat.error_prefix")}${describeError(err)}`
        revision.value += 1
      }
    } finally {
      isLoading.value = false
      abortController = null
      revision.value += 1
    }
  }

  /** 登录后接 WS；事件落到的位置由 wsTargetIndex 决定 */
  function connectWs(token: string): void {
    useWebSocket().connect(token, (event) => {
      applyEvent(event, wsTargetIndex)
    })
  }

  function disconnectWs(): void {
    useWebSocket().disconnect()
  }

  function reset(): void {
    disconnectWs()
    if (abortController) abortController.abort()
    abortController = null
    wsTargetIndex = -1
    messages.value = []
    isLoading.value = false
    sessionId.value = newSessionId()
    revision.value += 1
  }

  return { messages, isLoading, sessionId, revision, newChat, clearChat, loadHistory, selectSession, send, stop, connectWs, disconnectWs, reset }
}
