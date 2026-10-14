// 会话列表状态（模块级单例，`docs/rules/10-frontend-structure.md` R3/R4）：不 catch、不弹窗，错误由组件决定怎么显示。
import { ref } from "vue"
import * as api from "../api/client"
import type { SessionInfo } from "../api/types"

const sessions = ref<SessionInfo[]>([])

export function useSessions() {
  async function refresh(): Promise<void> {
    const data = await api.listSessions()
    sessions.value = data.sessions || []
  }

  function load(sessionId: string) {
    return api.getSession(sessionId)
  }

  async function remove(sessionId: string): Promise<void> {
    await api.deleteSession(sessionId)
    sessions.value = sessions.value.filter((s) => s.session_id !== sessionId)
  }

  function reset(): void {
    sessions.value = []
  }

  return { sessions, refresh, load, remove, reset }
}
