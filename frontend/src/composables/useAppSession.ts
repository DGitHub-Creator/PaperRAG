// 登录/登出时"整机状态"的收口（`docs/rules/10-frontend-structure.md` R3/R4）：
// 一次登录要开新会话并接 WS，一次登出要清掉聊天、会话列表与文档 job，
// 这两件事被 App.vue（启动/401）与 AppShell（点退出）共用，所以单独放在这里，避免两处各写一遍漏掉某一步。
import { useAuth } from "./useAuth"
import { useChat } from "./useChat"
import { useSessions } from "./useSessions"
import { useDocuments } from "./useDocuments"

export function useAppSession() {
  const auth = useAuth()
  const chat = useChat()
  const sessions = useSessions()
  const documents = useDocuments()

  /** 登出：清登录态 + 三个业务状态；跳转由调用方决定（401 与手动退出收尾不同） */
  function signOut(): void {
    auth.logout()
    chat.reset()
    sessions.reset()
    documents.reset()
  }

  /** 登录成功（含刷新页面恢复）：开一段新会话并接上 WS */
  function onSignedIn(token: string): void {
    chat.newChat()
    chat.connectWs(token)
  }

  return { signOut, onSignedIn }
}
