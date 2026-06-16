import { ref } from "vue"
import { authFetch } from "../services/api"
import { t } from "../i18n"

export interface SessionRecord {
  session_id: string
  message_count?: number
  updated_at?: string
}

interface SessionMessagesResponse {
  messages?: Array<{
    content: string
    type: string
    rag_trace?: unknown
  }>
}

export function useSessions() {
  const sessions = ref<SessionRecord[]>([])
  const showHistorySidebar = ref(false)

  async function list(): Promise<void> {
    try {
      const res = await authFetch("/sessions")
      if (!res.ok) throw new Error("加载失败")
      const data = await res.json()
      sessions.value = data.sessions || []
    } catch (e: unknown) { alert(t("history.load_failed") + (e instanceof Error ? e.message : String(e))) }
  }

  async function loadMessages(sessionId: string): Promise<SessionMessagesResponse | null> {
    try {
      const res = await authFetch(`/sessions/${encodeURIComponent(sessionId)}`)
      if (!res.ok) throw new Error("加载失败")
      return await res.json()
    } catch (e: unknown) { alert(t("history.load_session_failed") + (e instanceof Error ? e.message : String(e))); return null }
  }

  async function remove(sessionId: string): Promise<boolean> {
    if (!confirm(t("history.delete_confirm"))) return false
    try {
      const res = await authFetch(`/sessions/${encodeURIComponent(sessionId)}`, { method: "DELETE" })
      if (!res.ok) throw new Error("删除失败")
      sessions.value = sessions.value.filter((s) => s.session_id !== sessionId)
      return true
    } catch (e: unknown) { alert(t("history.delete_failed") + (e instanceof Error ? e.message : String(e))); return false }
  }

  return { sessions, showHistorySidebar, list, loadMessages, remove }
}
