// 登录态持久化的唯一所有者（`docs/rules/10-frontend-structure.md` R2）：
// 浏览器存储的键名与读写只出现在这个文件，其余层要么拿 `tokenStore.*`，要么完全不知道有存储。
import type { CurrentUserResponse } from "./types"

const TOKEN_KEY = "accessToken"
const USER_KEY = "currentUser"

export function readToken(): string {
  return localStorage.getItem(TOKEN_KEY) || ""
}

export function readStoredUser(): CurrentUserResponse | null {
  const raw = localStorage.getItem(USER_KEY)
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw) as Partial<CurrentUserResponse>
    if (typeof parsed.username !== "string" || typeof parsed.role !== "string") return null
    return { username: parsed.username, role: parsed.role }
  } catch (_) {
    // 手工改坏过的 localStorage 不该把启动流程一起带崩
    return null
  }
}

export function writeSession(token: string, user: CurrentUserResponse): void {
  localStorage.setItem(TOKEN_KEY, token)
  localStorage.setItem(USER_KEY, JSON.stringify(user))
}

export function writeUser(user: CurrentUserResponse): void {
  localStorage.setItem(USER_KEY, JSON.stringify(user))
}

export function clearSession(): void {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}
