// 登录态的唯一所有者：反应式状态在这里，持久化委托给 api/token.ts（`docs/rules/10-frontend-structure.md` R2）。
import { computed, ref } from "vue"
import * as api from "../api/client"
import { clearSession, readStoredUser, readToken, writeSession, writeUser } from "../api/token"
import type { AuthResponse, ChangePasswordRequest, CurrentUserResponse, Role } from "../api/types"

const token = ref(readToken())
const currentUser = ref<CurrentUserResponse | null>(readStoredUser())

export type AuthMode = "login" | "register"

/** AuthPanel 提交上来的载荷：mode 由组件持有，状态层只管"按 mode 走哪条接口" */
export interface AuthSubmit {
  mode: AuthMode
  username: string
  password: string
  role: Role
  admin_code: string | null
}

function applySession(nextToken: string, user: CurrentUserResponse | null): void {
  token.value = nextToken
  currentUser.value = user
  if (nextToken && user) writeSession(nextToken, user)
  else clearSession()
}

function toUser(auth: AuthResponse): CurrentUserResponse {
  return { username: auth.username, role: auth.role }
}

export function useAuth() {
  const isAuthenticated = computed(() => !!token.value && !!currentUser.value)
  const isAdmin = computed(() => currentUser.value?.role === "admin")
  const username = computed(() => currentUser.value?.username || "")
  const role = computed<string>(() => currentUser.value?.role || "")

  /** 启动时用本地 token 探测登录态；失败由调用方决定怎么收尾（401 已经广播过 auth-expired） */
  async function fetchMe(): Promise<void> {
    const user = await api.me()
    currentUser.value = user
    writeUser(user)
  }

  async function submit(input: AuthSubmit): Promise<void> {
    const auth =
      input.mode === "login"
        ? await api.login({ username: input.username, password: input.password })
        : await api.register({ username: input.username, password: input.password, role: input.role, admin_code: input.admin_code })
    applySession(auth.access_token, toUser(auth))
  }

  function logout(): void {
    applySession("", null)
  }

  /** 改密码：不重新签发 token（后端如此设计，旧 token 在 exp 前仍有效），所以这里也不动本地会话 */
  async function changePassword(input: ChangePasswordRequest): Promise<void> {
    await api.changePassword(input)
  }

  return { token, currentUser, isAuthenticated, isAdmin, username, role, fetchMe, submit, changePassword, logout }
}
