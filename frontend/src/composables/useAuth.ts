import { ref, computed } from "vue"
import { authFetch } from "../services/api"

interface UserInfo {
  username: string
  role: string
}

const token = ref<string>(localStorage.getItem("accessToken") || "")
const currentUser = ref<UserInfo | null>(null)

export function useAuth() {
  const isAuthenticated = computed(() => !!token.value && !!currentUser.value)
  const isAdmin = computed(() => currentUser.value?.role === "admin")
  const username = computed(() => currentUser.value?.username || "")

  function _persist(t: string, u: UserInfo | null) {
    token.value = t
    currentUser.value = u
    if (t) localStorage.setItem("accessToken", t)
    else localStorage.removeItem("accessToken")
    if (u) localStorage.setItem("currentUser", JSON.stringify(u))
    else localStorage.removeItem("currentUser")
  }

  async function fetchMe(): Promise<void> {
    const res = await authFetch("/auth/me")
    if (!res.ok) throw new Error("认证失败")
    currentUser.value = await res.json()
    localStorage.setItem("currentUser", JSON.stringify(currentUser.value))
  }

  async function login(username: string, password: string): Promise<void> {
    const res = await fetch("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(data.detail || "登录失败")
    _persist(data.access_token, { username: data.username, role: data.role })
  }

  async function register(username: string, password: string, role = "user", admin_code: string | null = null): Promise<void> {
    const res = await fetch("/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password, role, admin_code }),
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(data.detail || "注册失败")
    _persist(data.access_token, { username: data.username, role: data.role })
  }

  function logout(): void {
    _persist("", null)
  }

  return { token, currentUser, isAuthenticated, isAdmin, username, fetchMe, login, register, logout }
}
